"""PHX1-compatible PumpSwap fee classification with PHX2 proof enforcement.

The scoring rubric in this module is a literal Decimal-safe port of PHX1
``filters/fee_gate.py`` at commit ``318e359084d8711256747ae0fe307303d1b526d1``.
PHX1 used lifetime WSOL PumpSwap totals, binary floats and ``EPS=1e-9``.  PHX2
keeps the same formula, thresholds, flags and labels while representing every
boundary value as :class:`~decimal.Decimal`.

The immutable snapshot and proof checks are PHX2 safety additions.  They do not
change a valid PHX1 label; they prevent missing, malformed, stale, uncalibrated,
or inconsistent evidence from silently becoming eligible.
"""

from __future__ import annotations

import base64
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import statistics
import struct
import threading
from typing import Any, Deque, Dict, Iterable, Mapping, Optional, Tuple

from PHX2.free_tier_producer.liquidity_integrity import b58decode
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveError,
    decode_buy_event,
    decode_sell_event,
)
from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT,
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES,
    USDC_MINT,
)


PHX1_FEE_GATE_NORMAL = "Normal"
PHX1_FEE_GATE_ELEVATED = "Elevated"
PHX1_FEE_GATE_SUSPICIOUS = "Suspicious"
PHX1_FEE_GATE_SCAM_LIKELY = "SCAM Likely"
FEE_GATE_UNKNOWN = "UNKNOWN"
FEE_GATE_LABELS = frozenset({
    PHX1_FEE_GATE_NORMAL,
    PHX1_FEE_GATE_ELEVATED,
    PHX1_FEE_GATE_SUSPICIOUS,
    PHX1_FEE_GATE_SCAM_LIKELY,
    FEE_GATE_UNKNOWN,
})

REASON_BRIBES_STARVED = "bribes_starved"
REASON_BRIBES_LOW = "bribes_low"
REASON_CREATOR_DOMINANCE = "creator_dom_hi"
REASON_THIN_SAMPLE = "thin_sample"
REASON_INSUFFICIENT_DATA = "insufficient_data"
REASON_STICKY_LOCK = "sticky_lock"

BLOCK_SCAM_LIKELY = "PHX1_FEE_GATE_SCAM_LIKELY"
BLOCK_DATA_INVALID = "PHX1_FEE_GATE_DATA_INVALID"
BLOCK_DATA_STALE = "PHX1_FEE_GATE_DATA_STALE"
BLOCK_INSUFFICIENT_SAMPLE = "PHX1_FEE_GATE_INSUFFICIENT_SAMPLE"
BLOCK_PROOF_MISSING = "PHX1_FEE_GATE_PROOF_MISSING"
BLOCK_PROOF_INCONSISTENT = "PHX1_FEE_GATE_PROOF_INCONSISTENT"
BLOCK_PAIR_UNCALIBRATED = "PHX1_FEE_GATE_PAIR_UNCALIBRATED"

PHX1_EPS = Decimal("0.000000001")
PHX1_BRIBES_PCT_HARD = Decimal("2.81")
PHX1_BRIBES_PCT_SOFT = Decimal("5.0")
PHX1_CREATOR_DOMINANCE_HIGH = Decimal("0.70")
PHX1_TRANSACTION_COUNT_MIN = 500
PHX1_SUSPICIOUS_MIN = 3
PHX1_SCAM_LIKELY_MIN = 4
PHX1_BALANCED_BRIBES_PCT = Decimal("8.0")
PHX1_BALANCED_CREATOR_MAX = Decimal("0.35")

FEE_SNAPSHOT_VERSION = "PHX1_FEE_GATE_V2_PHX2_PROOF_V1"
FEE_SOURCE_PRIMARY = "PRIMARY_PUMPSWAP_STREAM"
LAMPORTS_PER_SOL = Decimal(1_000_000_000)
USDC_BASE_UNITS = Decimal(1_000_000)
DEFAULT_FEE_PROOF_MAX_AGE_SECONDS = Decimal("300")
RECENT_WINDOW_SECONDS = 300
ANTE_WINDOW_TRANSACTIONS = 20

COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"
JITO_TIP_ACCOUNTS = frozenset({
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMiK7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
})

# Raw 32-byte forms for the per-transaction fee fast path.  Comparing an account
# key against these bytes is exactly equivalent to base58-encoding the key and
# comparing the text, but avoids base58-encoding the whole account-key vector on
# every PumpSwap transaction just to locate the ComputeBudget and Jito accounts.
_COMPUTE_BUDGET_PROGRAM_ID_BYTES = b58decode(COMPUTE_BUDGET_PROGRAM_ID)
_JITO_TIP_ACCOUNT_BYTES = frozenset(b58decode(account) for account in JITO_TIP_ACCOUNTS)

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("decimal_bool_rejected")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("decimal_invalid")
    else:
        raise ValueError("binary_float_rejected")
    if not result.is_finite():
        raise ValueError("decimal_nonfinite")
    return result


def _dtext(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


def _share(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / (denominator + PHX1_EPS)


@dataclass(frozen=True)
class Phx1FeeScore:
    score: int
    flags: Tuple[str, ...]
    label: str
    creator_share: Decimal
    protocol_share: Decimal
    lp_share: Decimal
    bribes_pct_of_amm: Decimal
    bribes_per_tx: Decimal
    amm_per_tx: Decimal
    events_per_tx: Decimal


def score_phx1_fees(
    *,
    total_fee: object,
    lp_fee: object,
    protocol_fee: object,
    creator_fee: object,
    bribes: object,
    transaction_count: int,
    event_count: int,
) -> Phx1FeeScore:
    """Return the exact PHX1 v2 score using Decimal arithmetic.

    The unusual ``+ 1e-9`` denominator is intentionally preserved, including
    its exact-boundary behavior.
    """

    total = _decimal(total_fee)
    lp = _decimal(lp_fee)
    protocol = _decimal(protocol_fee)
    creator = _decimal(creator_fee)
    bribe = _decimal(bribes)
    if (isinstance(transaction_count, bool) or not isinstance(transaction_count, int)
            or isinstance(event_count, bool) or not isinstance(event_count, int)):
        raise ValueError("counts_must_be_int")
    if total <= 0 or transaction_count <= 0 or event_count <= 0:
        return Phx1FeeScore(
            score=0,
            flags=(REASON_INSUFFICIENT_DATA,),
            label=PHX1_FEE_GATE_NORMAL,
            creator_share=Decimal(0),
            protocol_share=Decimal(0),
            lp_share=Decimal(0),
            bribes_pct_of_amm=Decimal(0),
            bribes_per_tx=Decimal(0),
            amm_per_tx=Decimal(0),
            events_per_tx=Decimal(0),
        )
    if min(lp, protocol, creator, bribe) < 0:
        raise ValueError("negative_fee_component")
    creator_share = _share(creator, total)
    protocol_share = _share(protocol, total)
    lp_share = _share(lp, total)
    bribes_pct = _share(bribe, total) * Decimal(100)
    tx_denom = Decimal(transaction_count) + PHX1_EPS
    flags = []
    score = 0
    if bribes_pct < PHX1_BRIBES_PCT_HARD:
        score += 3
        flags.append(REASON_BRIBES_STARVED)
    elif bribes_pct < PHX1_BRIBES_PCT_SOFT:
        score += 1
        flags.append(REASON_BRIBES_LOW)
    if (creator_share >= PHX1_CREATOR_DOMINANCE_HIGH
            and bribes_pct < PHX1_BRIBES_PCT_SOFT):
        score += 2
        flags.append(REASON_CREATOR_DOMINANCE)
    if transaction_count < PHX1_TRANSACTION_COUNT_MIN:
        score += 1
        flags.append(REASON_THIN_SAMPLE)
    if score >= PHX1_SCAM_LIKELY_MIN:
        label = PHX1_FEE_GATE_SCAM_LIKELY
    elif score >= PHX1_SUSPICIOUS_MIN:
        label = PHX1_FEE_GATE_SUSPICIOUS
    elif score >= 1:
        label = PHX1_FEE_GATE_ELEVATED
    else:
        label = PHX1_FEE_GATE_NORMAL
    return Phx1FeeScore(
        score=score,
        flags=tuple(flags),
        label=label,
        creator_share=creator_share,
        protocol_share=protocol_share,
        lp_share=lp_share,
        bribes_pct_of_amm=bribes_pct,
        bribes_per_tx=bribe / tx_denom,
        amm_per_tx=total / tx_denom,
        events_per_tx=Decimal(event_count) / tx_denom,
    )


@dataclass(frozen=True)
class FeeEvent:
    candidate_mint: str
    quote_mint: str
    pair_type: str
    quote_asset: str
    unit: str
    transaction_signature: str
    event_index: int
    event_timestamp_epoch: int
    observed_at_utc: str
    side: str
    lp_fee_base_units: int
    protocol_fee_base_units: int
    creator_fee_base_units: int
    base_fee_base_units: int
    priority_fee_base_units: int
    jito_tip_base_units: int

    def __post_init__(self) -> None:
        if self.side not in ("BUY", "SELL"):
            raise ValueError("fee_event_side_invalid")
        for name in (
            "event_index", "event_timestamp_epoch", "lp_fee_base_units",
            "protocol_fee_base_units", "creator_fee_base_units",
            "base_fee_base_units", "priority_fee_base_units", "jito_tip_base_units",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name}_invalid")


@dataclass(frozen=True)
class FeeGateSnapshot:
    schema_version: str
    source: str
    candidate_mint: str
    quote_mint: Optional[str]
    quote_asset: Optional[str]
    pair_type: Optional[str]
    unit: Optional[str]
    total_fees: str
    lp_fees: str
    protocol_fees: str
    creator_fees: str
    transaction_fees: str
    base_fees: str
    priority_fees: str
    jito_tips: str
    bribes: str
    bribe_share_pct: str
    bribes_per_transaction: str
    lp_share: str
    protocol_share: str
    creator_share: str
    creator_dominance: bool
    balanced_fees: bool
    recent_transaction_count: int
    recent_swap_count: int
    recent_fee_median: Optional[str]
    ante_last20_median: Optional[str]
    ante_last20_p25: Optional[str]
    ante_last20_p75: Optional[str]
    ante_5m_median: Optional[str]
    ante_5m_p25: Optional[str]
    ante_5m_p75: Optional[str]
    ante_last20_sample_count: int
    ante_5m_sample_count: int
    ante_5m_base_fee_coverage: Optional[str]
    priority_fee_median_lamports: Optional[str]
    priority_fee_sample_count: int
    event_pace_per_minute: str
    observation_window: str
    sample_count: int
    transaction_count: int
    event_count: int
    first_observed_at_utc: Optional[str]
    last_observed_at_utc: Optional[str]
    evidence_observed_at_utc: str
    evidence_freshness_seconds: Optional[str]
    missing_data_reasons: Tuple[str, ...]
    stale_data_reasons: Tuple[str, ...]
    malformed_data_reasons: Tuple[str, ...]
    insufficient_sample_reasons: Tuple[str, ...]
    fee_gate_score: Optional[int]
    fee_gate_label: str
    fee_gate_reasons: Tuple[str, ...]
    fee_gate_eligible: bool
    hard_block: bool
    proof_digest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        for key in (
            "missing_data_reasons", "stale_data_reasons", "malformed_data_reasons",
            "insufficient_sample_reasons", "fee_gate_reasons",
        ):
            value[key] = list(value[key])
        return value


def _proof_payload(snapshot: FeeGateSnapshot) -> Dict[str, Any]:
    payload = snapshot.to_dict()
    payload.pop("proof_digest", None)
    return payload


def _proof_digest(snapshot: FeeGateSnapshot) -> str:
    raw = json.dumps(_proof_payload(snapshot), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seal_fee_snapshot(snapshot: FeeGateSnapshot) -> FeeGateSnapshot:
    return replace(snapshot, proof_digest=_proof_digest(replace(snapshot, proof_digest="")))


def _percentiles(values: Iterable[Decimal]) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    rows = sorted(values)
    if not rows:
        return None, None, None
    if len(rows) == 1:
        return rows[0], rows[0], rows[0]
    # PHX1 used statistics.quantiles(..., method="inclusive") over floats.
    as_float = [float(value) for value in rows]
    quartiles = statistics.quantiles(as_float, n=4, method="inclusive")
    return Decimal(str(quartiles[0])), Decimal(str(statistics.median(as_float))), Decimal(str(quartiles[2]))


class FeeEvidenceIndex:
    """Thread-safe, bounded raw-event owner with lifetime aggregate counters."""

    def __init__(self, *, dedupe_limit: int = 200_000, recent_limit: int = 4096) -> None:
        self._lock = threading.Lock()
        self._dedupe_limit = max(1024, int(dedupe_limit))
        self._recent_limit = max(64, int(recent_limit))
        self._dedupe: "OrderedDict[Tuple[str, int], None]" = OrderedDict()
        self._by_mint: Dict[str, Dict[str, Any]] = {}
        self._decoded = 0
        self._rejected = 0

    def record(self, event: FeeEvent) -> bool:
        if not isinstance(event, FeeEvent):
            with self._lock:
                self._rejected += 1
            return False
        key = (event.transaction_signature, event.event_index)
        with self._lock:
            if key in self._dedupe:
                return False
            self._dedupe[key] = None
            while len(self._dedupe) > self._dedupe_limit:
                self._dedupe.popitem(last=False)
            state = self._by_mint.setdefault(event.candidate_mint, {
                "quote_mint": event.quote_mint,
                "quote_asset": event.quote_asset,
                "pair_type": event.pair_type,
                "unit": event.unit,
                "lp": 0,
                "protocol": 0,
                "creator": 0,
                "base": 0,
                "priority": 0,
                "jito": 0,
                "events": 0,
                "signatures": set(),
                "first": event.observed_at_utc,
                "last": event.observed_at_utc,
                "last_epoch": event.event_timestamp_epoch,
                "recent": deque(maxlen=self._recent_limit),
                "tx_ante": OrderedDict(),
            })
            if (state["quote_mint"] != event.quote_mint
                    or state["unit"] != event.unit):
                self._rejected += 1
                return False
            state["lp"] += event.lp_fee_base_units
            state["protocol"] += event.protocol_fee_base_units
            state["creator"] += event.creator_fee_base_units
            state["base"] += event.base_fee_base_units
            state["priority"] += event.priority_fee_base_units
            state["jito"] += event.jito_tip_base_units
            state["events"] += 1
            state["signatures"].add(event.transaction_signature)
            state["last"] = event.observed_at_utc
            state["last_epoch"] = max(state["last_epoch"], event.event_timestamp_epoch)
            state["recent"].append(event)
            if event.transaction_signature not in state["tx_ante"]:
                state["tx_ante"][event.transaction_signature] = (
                    event.event_timestamp_epoch,
                    event.base_fee_base_units + event.priority_fee_base_units + event.jito_tip_base_units,
                    event.base_fee_base_units,
                    event.priority_fee_base_units,
                )
                while len(state["tx_ante"]) > self._recent_limit:
                    state["tx_ante"].popitem(last=False)
            self._decoded += 1
            return True

    def snapshot(self, mint: str, *, now_epoch: int,
                 max_age_seconds: object = DEFAULT_FEE_PROOF_MAX_AGE_SECONDS) -> FeeGateSnapshot:
        with self._lock:
            raw = self._by_mint.get(str(mint))
            state = None if raw is None else {
                **raw,
                "signatures": set(raw["signatures"]),
                "recent": tuple(raw["recent"]),
                "tx_ante": tuple(raw["tx_ante"].values()),
            }
        # The historical worst-score sticky override was removed here: it let
        # an early immature classification (e.g. bribes_starved + thin_sample
        # on a brand-new pool) permanently poison every later healthy snapshot.
        # Durable scam locks are now owned by the fee gate lifecycle
        # (PHX2.free_tier_producer.fee_gate_lifecycle), which requires fresh,
        # mature, structurally reasoned scam evidence confirmed across distinct
        # evidence versions before it stamps ``sticky_lock`` back onto a
        # snapshot.  This method is a pure read of the evidence index.
        return build_fee_snapshot(
            str(mint), state=state, now_epoch=now_epoch,
            max_age_seconds=max_age_seconds)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "fee_events_decoded": self._decoded,
                "fee_events_rejected": self._rejected,
                "fee_mints_indexed": len(self._by_mint),
            }


def _unknown_snapshot(mint: str, *, observed_at: str, reason: str,
                      category: str) -> FeeGateSnapshot:
    missing = (reason,) if category == "missing" else ()
    stale = (reason,) if category == "stale" else ()
    malformed = (reason,) if category == "malformed" else ()
    insufficient = (reason,) if category == "insufficient" else ()
    return seal_fee_snapshot(FeeGateSnapshot(
        schema_version=FEE_SNAPSHOT_VERSION,
        source=FEE_SOURCE_PRIMARY,
        candidate_mint=mint,
        quote_mint=None,
        quote_asset=None,
        pair_type=None,
        unit=None,
        total_fees="0",
        lp_fees="0",
        protocol_fees="0",
        creator_fees="0",
        transaction_fees="0",
        base_fees="0",
        priority_fees="0",
        jito_tips="0",
        bribes="0",
        bribe_share_pct="0",
        bribes_per_transaction="0",
        lp_share="0",
        protocol_share="0",
        creator_share="0",
        creator_dominance=False,
        balanced_fees=False,
        recent_transaction_count=0,
        recent_swap_count=0,
        recent_fee_median=None,
        ante_last20_median=None,
        ante_last20_p25=None,
        ante_last20_p75=None,
        ante_5m_median=None,
        ante_5m_p25=None,
        ante_5m_p75=None,
        ante_last20_sample_count=0,
        ante_5m_sample_count=0,
        ante_5m_base_fee_coverage=None,
        priority_fee_median_lamports=None,
        priority_fee_sample_count=0,
        event_pace_per_minute="0",
        observation_window="LIFETIME_SINCE_PRIMARY_STREAM_START",
        sample_count=0,
        transaction_count=0,
        event_count=0,
        first_observed_at_utc=None,
        last_observed_at_utc=None,
        evidence_observed_at_utc=observed_at,
        evidence_freshness_seconds=None,
        missing_data_reasons=missing,
        stale_data_reasons=stale,
        malformed_data_reasons=malformed,
        insufficient_sample_reasons=insufficient,
        fee_gate_score=None,
        fee_gate_label=FEE_GATE_UNKNOWN,
        fee_gate_reasons=(reason,),
        fee_gate_eligible=False,
        hard_block=True,
    ))


def build_fee_snapshot(mint: str, *, state: Optional[Mapping[str, Any]],
                       now_epoch: int,
                       max_age_seconds: object = DEFAULT_FEE_PROOF_MAX_AGE_SECONDS) -> FeeGateSnapshot:
    observed_at = datetime.fromtimestamp(int(now_epoch), timezone.utc).isoformat().replace("+00:00", "Z")
    if not state:
        return _unknown_snapshot(
            mint, observed_at=observed_at, reason=BLOCK_PROOF_MISSING, category="missing")
    try:
        max_age = _decimal(max_age_seconds)
        unit = str(state["unit"])
        divisor = LAMPORTS_PER_SOL if unit == "SOL" else USDC_BASE_UNITS if unit == "USDC" else None
        if divisor is None:
            return _unknown_snapshot(
                mint, observed_at=observed_at, reason=BLOCK_DATA_INVALID, category="malformed")
        last_epoch = int(state["last_epoch"])
        age = Decimal(int(now_epoch) - last_epoch)
        if age < 0 or age > max_age:
            return _unknown_snapshot(
                mint, observed_at=observed_at, reason=BLOCK_DATA_STALE, category="stale")
        if unit != "SOL" or state.get("quote_mint") == USDC_MINT:
            # PHX1 had no USDC calibration universe.  Preserve separation and fail closed.
            return _unknown_snapshot(
                mint, observed_at=observed_at, reason=BLOCK_PAIR_UNCALIBRATED, category="insufficient")
        lp = Decimal(int(state["lp"])) / divisor
        protocol = Decimal(int(state["protocol"])) / divisor
        creator = Decimal(int(state["creator"])) / divisor
        total = lp + protocol + creator
        base = Decimal(int(state["base"])) / divisor
        priority = Decimal(int(state["priority"])) / divisor
        jito = Decimal(int(state["jito"])) / divisor
        bribes = priority + jito
        transaction_count = len(state["signatures"])
        event_count = int(state["events"])
        if total <= 0 or transaction_count <= 0 or event_count <= 0:
            return _unknown_snapshot(
                mint, observed_at=observed_at,
                reason=BLOCK_INSUFFICIENT_SAMPLE, category="insufficient")
        score = score_phx1_fees(
            total_fee=total, lp_fee=lp, protocol_fee=protocol,
            creator_fee=creator, bribes=bribes,
            transaction_count=transaction_count, event_count=event_count)
        recent_events = [
            event for event in state["recent"]
            if int(now_epoch) - int(event.event_timestamp_epoch) <= RECENT_WINDOW_SECONDS
        ]
        recent_signatures = {event.transaction_signature for event in recent_events}
        tx_ante_rows = [tuple(row) for row in state["tx_ante"]]
        recent_ante_rows = [
            row for row in tx_ante_rows
            if len(row) >= 2
            and int(now_epoch) - int(row[0]) <= RECENT_WINDOW_SECONDS
        ]
        last20_rows = [
            row for row in tx_ante_rows[-ANTE_WINDOW_TRANSACTIONS:]
            if len(row) >= 2
        ]
        recent_ante_units = [Decimal(row[1]) / divisor for row in recent_ante_rows]
        last20_units = [Decimal(row[1]) / divisor for row in last20_rows]
        a20_p25, a20_med, a20_p75 = _percentiles(last20_units)
        a5_p25, a5_med, a5_p75 = _percentiles(recent_ante_units)
        recent_base_rows = [row for row in recent_ante_rows if len(row) >= 4]
        base_fee_coverage = (
            None if not recent_base_rows else
            Decimal(sum(1 for row in recent_base_rows if int(row[2]) > 0))
            / Decimal(len(recent_base_rows))
        )
        priority_rows = [
            Decimal(int(row[3])) for row in last20_rows if len(row) >= 4
        ]
        priority_median = (
            None if not priority_rows else
            Decimal(str(statistics.median([int(value) for value in priority_rows])))
        )
        recent_totals = [
            Decimal(event.lp_fee_base_units + event.protocol_fee_base_units
                    + event.creator_fee_base_units) / divisor
            for event in recent_events
        ]
        recent_fee_median = (None if not recent_totals
                             else Decimal(str(statistics.median([float(v) for v in recent_totals]))))
        reasons = list(score.flags)
        hard_block = score.label == PHX1_FEE_GATE_SCAM_LIKELY
        if hard_block:
            reasons.append(BLOCK_SCAM_LIKELY)
        balanced = (
            not score.flags
            and score.bribes_pct_of_amm >= PHX1_BALANCED_BRIBES_PCT
            and score.creator_share < PHX1_BALANCED_CREATOR_MAX
        )
        return seal_fee_snapshot(FeeGateSnapshot(
            schema_version=FEE_SNAPSHOT_VERSION,
            source=FEE_SOURCE_PRIMARY,
            candidate_mint=mint,
            quote_mint=str(state["quote_mint"]),
            quote_asset=str(state["quote_asset"]),
            pair_type=str(state["pair_type"]),
            unit=unit,
            total_fees=_dtext(total) or "0",
            lp_fees=_dtext(lp) or "0",
            protocol_fees=_dtext(protocol) or "0",
            creator_fees=_dtext(creator) or "0",
            transaction_fees=_dtext(base + priority + jito) or "0",
            base_fees=_dtext(base) or "0",
            priority_fees=_dtext(priority) or "0",
            jito_tips=_dtext(jito) or "0",
            bribes=_dtext(bribes) or "0",
            bribe_share_pct=_dtext(score.bribes_pct_of_amm) or "0",
            bribes_per_transaction=_dtext(score.bribes_per_tx) or "0",
            lp_share=_dtext(score.lp_share) or "0",
            protocol_share=_dtext(score.protocol_share) or "0",
            creator_share=_dtext(score.creator_share) or "0",
            creator_dominance=(score.creator_share >= PHX1_CREATOR_DOMINANCE_HIGH),
            balanced_fees=balanced,
            recent_transaction_count=len(recent_signatures),
            recent_swap_count=len(recent_events),
            recent_fee_median=_dtext(recent_fee_median),
            ante_last20_median=_dtext(a20_med),
            ante_last20_p25=_dtext(a20_p25),
            ante_last20_p75=_dtext(a20_p75),
            ante_5m_median=_dtext(a5_med),
            ante_5m_p25=_dtext(a5_p25),
            ante_5m_p75=_dtext(a5_p75),
            ante_last20_sample_count=len(last20_rows),
            ante_5m_sample_count=len(recent_ante_rows),
            ante_5m_base_fee_coverage=_dtext(base_fee_coverage),
            priority_fee_median_lamports=_dtext(priority_median),
            priority_fee_sample_count=len(priority_rows),
            event_pace_per_minute=_dtext(Decimal(len(recent_events)) / Decimal(5)) or "0",
            observation_window="LIFETIME_SINCE_PRIMARY_STREAM_START;PACE_300S;ANTE_LAST20_AND_300S",
            sample_count=event_count,
            transaction_count=transaction_count,
            event_count=event_count,
            first_observed_at_utc=str(state["first"]),
            last_observed_at_utc=str(state["last"]),
            evidence_observed_at_utc=observed_at,
            evidence_freshness_seconds=_dtext(age),
            missing_data_reasons=(),
            stale_data_reasons=(),
            malformed_data_reasons=(),
            insufficient_sample_reasons=(),
            fee_gate_score=score.score,
            fee_gate_label=score.label,
            fee_gate_reasons=tuple(reasons),
            fee_gate_eligible=not hard_block,
            hard_block=hard_block,
        ))
    except Exception:
        return _unknown_snapshot(
            mint, observed_at=observed_at, reason=BLOCK_DATA_INVALID, category="malformed")


def validate_fee_snapshot(snapshot: object) -> Tuple[bool, Optional[str]]:
    if not isinstance(snapshot, FeeGateSnapshot):
        return False, BLOCK_PROOF_MISSING
    if snapshot.schema_version != FEE_SNAPSHOT_VERSION or snapshot.source != FEE_SOURCE_PRIMARY:
        return False, BLOCK_PROOF_INCONSISTENT
    if not snapshot.proof_digest or snapshot.proof_digest != _proof_digest(snapshot):
        return False, BLOCK_PROOF_INCONSISTENT
    if snapshot.fee_gate_label not in FEE_GATE_LABELS:
        return False, BLOCK_PROOF_INCONSISTENT
    try:
        total = _decimal(snapshot.total_fees)
        lp = _decimal(snapshot.lp_fees)
        protocol = _decimal(snapshot.protocol_fees)
        creator = _decimal(snapshot.creator_fees)
        base = _decimal(snapshot.base_fees)
        priority = _decimal(snapshot.priority_fees)
        jito = _decimal(snapshot.jito_tips)
        bribes = _decimal(snapshot.bribes)
        components = lp + protocol + creator
        if total != components:
            return False, BLOCK_PROOF_INCONSISTENT
        if _decimal(snapshot.transaction_fees) != base + priority + jito:
            return False, BLOCK_PROOF_INCONSISTENT
        if bribes != priority + jito:
            return False, BLOCK_PROOF_INCONSISTENT
    except ValueError:
        return False, BLOCK_DATA_INVALID
    if snapshot.fee_gate_label == FEE_GATE_UNKNOWN:
        reason_sets = (
            snapshot.missing_data_reasons, snapshot.stale_data_reasons,
            snapshot.malformed_data_reasons, snapshot.insufficient_sample_reasons,
        )
        if (snapshot.fee_gate_score is not None or snapshot.sample_count != 0
                or not any(reason_sets) or not snapshot.fee_gate_reasons
                or snapshot.fee_gate_eligible or not snapshot.hard_block):
            return False, BLOCK_PROOF_INCONSISTENT
        return True, None
    if (snapshot.unit != "SOL" or snapshot.quote_asset != "SOL"
            or snapshot.quote_mint == USDC_MINT
            or snapshot.sample_count != snapshot.event_count
            or snapshot.transaction_count <= 0 or snapshot.event_count <= 0
            or snapshot.fee_gate_score is None):
        return False, BLOCK_PROOF_INCONSISTENT
    try:
        freshness = _decimal(snapshot.evidence_freshness_seconds)
        if freshness < 0 or freshness > DEFAULT_FEE_PROOF_MAX_AGE_SECONDS:
            return False, BLOCK_DATA_STALE
        recomputed = score_phx1_fees(
            total_fee=total, lp_fee=lp, protocol_fee=protocol,
            creator_fee=creator, bribes=bribes,
            transaction_count=snapshot.transaction_count,
            event_count=snapshot.event_count,
        )
    except ValueError:
        return False, BLOCK_DATA_INVALID
    sticky = REASON_STICKY_LOCK in snapshot.fee_gate_reasons
    if not sticky:
        expected_reasons = list(recomputed.flags)
        if recomputed.label == PHX1_FEE_GATE_SCAM_LIKELY:
            expected_reasons.append(BLOCK_SCAM_LIKELY)
        expected_balanced = (
            not recomputed.flags
            and recomputed.bribes_pct_of_amm >= PHX1_BALANCED_BRIBES_PCT
            and recomputed.creator_share < PHX1_BALANCED_CREATOR_MAX)
        exact_values = (
            snapshot.fee_gate_score == recomputed.score,
            snapshot.fee_gate_label == recomputed.label,
            snapshot.fee_gate_reasons == tuple(expected_reasons),
            _decimal(snapshot.bribe_share_pct) == recomputed.bribes_pct_of_amm,
            _decimal(snapshot.bribes_per_transaction) == recomputed.bribes_per_tx,
            _decimal(snapshot.lp_share) == recomputed.lp_share,
            _decimal(snapshot.protocol_share) == recomputed.protocol_share,
            _decimal(snapshot.creator_share) == recomputed.creator_share,
            snapshot.creator_dominance == (
                recomputed.creator_share >= PHX1_CREATOR_DOMINANCE_HIGH),
            snapshot.balanced_fees == expected_balanced,
        )
        if not all(exact_values):
            return False, BLOCK_PROOF_INCONSISTENT
    if snapshot.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY:
        if snapshot.fee_gate_eligible or not snapshot.hard_block:
            return False, BLOCK_PROOF_INCONSISTENT
    elif not snapshot.fee_gate_eligible or snapshot.hard_block:
        return False, BLOCK_PROOF_INCONSISTENT
    return True, None


def fee_gate_block_reason(snapshot: object) -> Optional[str]:
    valid, reason = validate_fee_snapshot(snapshot)
    if not valid:
        return reason or BLOCK_PROOF_INCONSISTENT
    assert isinstance(snapshot, FeeGateSnapshot)
    if snapshot.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY:
        return BLOCK_SCAM_LIKELY
    if snapshot.hard_block or not snapshot.fee_gate_eligible:
        return snapshot.fee_gate_reasons[-1] if snapshot.fee_gate_reasons else BLOCK_PROOF_INCONSISTENT
    return None


def format_fee_gate_lines(snapshot: FeeGateSnapshot) -> Tuple[str, ...]:
    reasons = ",".join(snapshot.fee_gate_reasons) if snapshot.fee_gate_reasons else "none"
    hundred = Decimal("100")
    unit = snapshot.unit or "UNKNOWN"
    ante20 = snapshot.ante_last20_median or "UNKNOWN"
    ante5m = snapshot.ante_5m_median or "UNKNOWN"
    return (
        f"Fee Gate: {snapshot.fee_gate_label}",
        f"Fee Gate reasons: {reasons}",
        ("Bribes %%: %s | Creator %%: %s | LP/AMM %%: %s | Protocol %%: %s"
         % (snapshot.bribe_share_pct, _decimal(snapshot.creator_share) * hundred,
            _decimal(snapshot.lp_share) * hundred,
            _decimal(snapshot.protocol_share) * hundred)),
        f"Bribes/tx: {snapshot.bribes_per_transaction} {unit}",
        f"balanced_fees: {str(snapshot.balanced_fees).lower()}",
        (f"Participation: total={snapshot.total_fees} {unit} "
         f"LP={snapshot.lp_fees} protocol={snapshot.protocol_fees} "
         f"creator={snapshot.creator_fees} tx_fees={snapshot.transaction_fees}"),
        (f"Events: count={snapshot.event_count} tx={snapshot.transaction_count} "
         f"pace={snapshot.event_pace_per_minute}/min"),
        (f"Ante: last20_median={ante20} {unit} "
         f"5m_median={ante5m} {unit}"),
    )


def _base58(raw: bytes) -> str:
    zeros = len(raw) - len(raw.lstrip(b"\x00"))
    number = int.from_bytes(raw, "big")
    chars = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_BASE58_ALPHABET[rem])
    return "1" * zeros + "".join(reversed(chars))


def _program_data_payloads(logs: Iterable[object]) -> Iterable[bytes]:
    prefix = "Program data: "
    for value in logs:
        if isinstance(value, str) and value.startswith(prefix):
            try:
                yield base64.b64decode(value[len(prefix):], validate=True)
            except (ValueError, TypeError):
                continue


def _token_context(meta: object) -> Tuple[Optional[str], Optional[str]]:
    mints = set()
    for attr in ("pre_token_balances", "post_token_balances"):
        for balance in list(getattr(meta, attr, ()) or ()):
            mint = getattr(balance, "mint", None)
            if isinstance(mint, str) and mint:
                mints.add(mint)
    base = [mint for mint in mints if mint not in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT]
    quote = [mint for mint in mints if mint in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT]
    return (base[0] if len(base) == 1 else None,
            quote[0] if len(quote) == 1 else None)


def _full_key_bytes(tx_info: object) -> list[bytes]:
    """Raw account-key bytes (message + loaded writable/readonly), in order.

    Returns raw 32-byte keys rather than base58 text: the fee fast path only
    compares keys against known program-id / Jito-account bytes, so encoding
    every key to base58 on every transaction is pure waste.
    """
    try:
        message = tx_info.transaction.message
        keys = [bytes(key) for key in list(message.account_keys)]
        meta = tx_info.meta
        keys += [bytes(key) for key in list(meta.loaded_writable_addresses)]
        keys += [bytes(key) for key in list(meta.loaded_readonly_addresses)]
        return keys
    except Exception:
        return []


def _tx_fees(tx_info: object) -> Tuple[int, int, int]:
    try:
        meta = tx_info.meta
        message = tx_info.transaction.message
        base_fee = int(meta.fee)
        cu = int(meta.compute_units_consumed) if meta.HasField("compute_units_consumed") else 0
        keys = _full_key_bytes(tx_info)
        micro = 0
        for instruction in list(message.instructions):
            index = int(instruction.program_id_index)
            if not (0 <= index < len(keys)) or keys[index] != _COMPUTE_BUDGET_PROGRAM_ID_BYTES:
                continue
            data = bytes(instruction.data)
            if len(data) >= 9 and data[0] == 3:
                micro = struct.unpack("<Q", data[1:9])[0]
                break
        priority = (micro * cu + 999_999) // 1_000_000 if micro and cu else 0
        jito = 0
        pre = list(meta.pre_balances)
        post = list(meta.post_balances)
        for index in range(min(len(keys), len(pre), len(post))):
            if keys[index] in _JITO_TIP_ACCOUNT_BYTES:
                delta = int(post[index]) - int(pre[index])
                if delta > 0:
                    jito += delta
        return max(0, base_fee), max(0, priority), max(0, jito)
    except Exception:
        return 0, 0, 0


def ingest_fee_events_from_update(update: object, *, fee_index: FeeEvidenceIndex) -> int:
    """Decode exact Buy/Sell fee events from the already-open primary stream."""

    if not isinstance(fee_index, FeeEvidenceIndex):
        return 0
    try:
        tx_info = update.transaction.transaction
        meta = tx_info.meta
        signature_raw = bytes(tx_info.signature)
        signature = _base58(signature_raw)
    except Exception:
        return 0
    mint, quote_mint = _token_context(meta)
    if mint is None or quote_mint is None:
        return 0
    pair_type = KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT.get(quote_mint)
    quote_asset = KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT.get(quote_mint)
    if not pair_type or not quote_asset:
        return 0
    unit = "USDC" if quote_mint == USDC_MINT else "SOL"
    base_fee, priority_fee, jito_tip = _tx_fees(tx_info)
    count = 0
    event_index = 0
    for payload in _program_data_payloads(list(getattr(meta, "log_messages", ()) or ())):
        side = None
        try:
            if payload.startswith(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES):
                artifact = decode_buy_event(payload, base_mint=mint, quote_mint=quote_mint)
                side = "BUY"
            elif payload.startswith(PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES):
                artifact = decode_sell_event(payload, base_mint=mint, quote_mint=quote_mint)
                side = "SELL"
            else:
                continue
            if len(payload) < 360:
                raise PumpSwapReserveError("fee_event_too_short")
            lp_fee = struct.unpack_from("<Q", payload, 80)[0]
            protocol_fee = struct.unpack_from("<Q", payload, 96)[0]
            creator_fee = struct.unpack_from("<Q", payload, 352)[0]
            timestamp = int(artifact.event_timestamp or 0)
            observed = datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")
            event = FeeEvent(
                candidate_mint=mint,
                quote_mint=quote_mint,
                pair_type=str(pair_type),
                quote_asset=str(quote_asset),
                unit=unit,
                transaction_signature=signature,
                event_index=event_index,
                event_timestamp_epoch=timestamp,
                observed_at_utc=observed,
                side=side,
                lp_fee_base_units=lp_fee,
                protocol_fee_base_units=protocol_fee,
                creator_fee_base_units=creator_fee,
                base_fee_base_units=(base_fee if event_index == 0 else 0),
                priority_fee_base_units=(priority_fee if event_index == 0 else 0),
                jito_tip_base_units=(jito_tip if event_index == 0 else 0),
            )
            if fee_index.record(event):
                count += 1
            event_index += 1
        except (PumpSwapReserveError, ValueError, struct.error, OverflowError):
            if side is not None:
                event_index += 1
            continue
    return count


__all__ = (
    "PHX1_FEE_GATE_NORMAL", "PHX1_FEE_GATE_ELEVATED", "PHX1_FEE_GATE_SUSPICIOUS",
    "PHX1_FEE_GATE_SCAM_LIKELY", "FEE_GATE_UNKNOWN", "FEE_GATE_LABELS",
    "BLOCK_SCAM_LIKELY", "BLOCK_DATA_INVALID", "BLOCK_DATA_STALE",
    "BLOCK_INSUFFICIENT_SAMPLE", "BLOCK_PROOF_MISSING", "BLOCK_PROOF_INCONSISTENT",
    "PHX1_EPS", "PHX1_BRIBES_PCT_HARD", "PHX1_BRIBES_PCT_SOFT",
    "PHX1_CREATOR_DOMINANCE_HIGH", "PHX1_TRANSACTION_COUNT_MIN",
    "FeeEvent", "FeeGateSnapshot", "FeeEvidenceIndex", "Phx1FeeScore",
    "score_phx1_fees", "build_fee_snapshot", "seal_fee_snapshot",
    "validate_fee_snapshot", "fee_gate_block_reason", "format_fee_gate_lines",
    "ingest_fee_events_from_update",
)
