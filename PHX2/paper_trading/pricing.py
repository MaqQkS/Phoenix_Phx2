"""Normalize PHX2 candidate/ping artifact JSONL records into snapshots.

Understands the real PHX2 artifact shapes that exist today:

* ``BUILD30_CANDIDATE_RECHECK`` records (per-mint recheck series with
  ``market_attempt_summary`` price/market-cap/liquidity, plus
  ``compose_tier`` / ``compose_drawdown_pct`` / ``compose_anchored_ath_mc``
  when the dip gate evaluated the candidate),
* watch-state seed records (mint + timestamps, usually price-less),
* any generic record carrying a mint plus a timestamp, with tolerant
  key aliases for price / market cap / liquidity / volume / tier / score.

Missing fields never crash normalization: they come back ``None`` and the
engine decides what that means (skip entry, data-lost, etc.).
"""

from __future__ import annotations

import glob as _glob
import bisect
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PHX2.paper_trading.models import (
    CandidateSnapshot,
    parse_money_text,
    parse_number,
    parse_pct_text,
    parse_tier,
    parse_utc,
)
from PHX2.paper_trading.risk import parse_risk_label, parse_risk_reasons

# Key aliases, first hit wins. Checked on the record root, then on the
# nested containers listed in _NESTED_CONTAINERS.
_MINT_KEYS = ("token_mint", "mint", "base_mint", "token_address")
_TS_KEYS = ("observed_at_utc", "ts_utc", "timestamp_utc", "timestamp",
            "attempt_at_utc", "fetched_at_utc", "market_context_fetched_at_utc",
            "created_at_utc", "last_observed_at_utc", "seeded_at_utc",
            "sent_at_utc")
_PRICE_KEYS = ("current_price", "price_usd", "price", "price_value")
_MC_KEYS = ("current_market_cap_usd", "market_cap_usd", "mc_usd", "mc_value",
            "market_cap")
_LP_KEYS = ("liquidity_usd", "lp_usd", "lp_value", "liquidity")
_VOLUME_KEYS = ("volume_usd", "recent_volume_usd", "volume_24h_usd",
                "volume_usd_24h")
_TIER_KEYS = ("compose_tier", "tier", "phx2_tier")
_DRAWDOWN_KEYS = ("compose_drawdown_pct", "drawdown_pct", "dip_pct")
_ATH_KEYS = ("compose_anchored_ath_mc", "anchored_ath_mc",
             "ath_market_cap_usd", "ath_mc_usd")
_SCORE_KEYS = ("score", "quality_score", "quality")
_SYMBOL_KEYS = ("token_symbol", "symbol", "symbol_or_name", "token_name",
                "name")
_SUPPLY_KEYS = ("supply", "token_supply", "circulating_supply")
_CANDIDATE_ID_KEYS = ("candidate_id", "ping_id", "artifact_id", "id")
_RISK_LABEL_KEYS = ("risk_label",)
_RISK_REASON_KEYS = ("risk_reasons",)

_NESTED_CONTAINERS = ("market_attempt_summary", "market_context", "market",
                      "context", "central_ath")

# Producer-internal bookkeeping files that live in the same out dir but are NOT paper
# input streams. polling_seen.jsonl is the polling-discovery dedupe ledger (pool/sig
# markers, no mint/price); tailing it only produced benign decode noise in the paper
# error ledger (79 PARSE_ERRORs on 2026-07-11's live_private_03 run).
EXCLUDED_INPUT_BASENAMES = frozenset({"polling_seen.jsonl"})
PRODUCER_INPUT_KINDS = frozenset({"BUILD30_CANDIDATE_RECHECK", "FREE_TIER_PRICING_TAIL"})


def _as_of(evidence: Dict[str, Any], epoch: float, *, external: bool = False) -> bool:
    """Both event time and time learned must precede the consuming observation."""
    keys = ("ath_timestamp", "ath_ingested_at_utc", "last_updated_at",
            "resolved_observed_at_utc", "activated_at_utc", "activation_observed_at_utc",
            "activation_evidence_event_at_utc", "activation_evidence_ingested_at_utc")
    times = [parse_utc(evidence[k]) for k in keys if evidence.get(k) is not None]
    if any(value is None or value > epoch for value in times):
        return False
    # A sibling state file is not historical evidence without a known-at time.
    return not external or any(evidence.get(k) is not None for k in (
        "ath_ingested_at_utc", "last_updated_at"))


def _first(record: Dict[str, Any], containers: List[Dict[str, Any]],
           keys: Tuple[str, ...]) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    for container in containers:
        for key in keys:
            if key in container and container[key] is not None:
                return container[key]
    return None


def _last_attempt(record: Dict[str, Any]) -> Dict[str, Any]:
    summary = record.get("market_attempt_summary")
    if isinstance(summary, dict):
        attempts = summary.get("attempts")
        if isinstance(attempts, list) and attempts:
            last = attempts[-1]
            if isinstance(last, dict):
                return last
    return {}


def _validated_reserve_telemetry(
    record: Dict[str, Any], containers: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Return only centrally-derived, decoder-proven PumpSwap telemetry.

    The paper adapter never reconstructs price from raw reserves.  A raw-only
    record therefore remains price-less instead of accidentally reviving the
    legacy formula.
    """

    candidates = [record.get("pumpswap_reserve")]
    candidates.extend(container.get("pumpswap_reserve") for container in containers)
    for value in candidates:
        if not isinstance(value, dict) or value.get("reserve_validation_status") != "VALID":
            continue
        artifact = value.get("reserve_artifact")
        if not isinstance(artifact, dict):
            continue
        required = (
            "raw_quote_reserves", "virtual_quote_reserves",
            "effective_quote_reserves", "base_reserves", "reserve_source",
            "observation_timestamp", "decoder_layout_version",
        )
        if all(artifact.get(key) is not None for key in required):
            return value
    return {}


def _load_central_ath_for_input(file_path: str) -> Dict[str, Dict[str, Any]]:
    """Read the producer's atomic central ATH artifact beside a JSONL input."""
    path = Path(file_path)
    root = path.parent.parent if path.parent.name == "candidates" else path.parent
    root = root.resolve()
    if "phoenix_bot" in [part.lower() for part in path.resolve().parts]:
        return {}
    candidates = (path.parent / "ath_state.json", root / "ath_state.json")
    for state_path in candidates:
        try:
            target = state_path.resolve()
            if (state_path.is_symlink() or state_path.is_junction()
                    or not target.is_relative_to(root)
                    or "phoenix_bot" in [part.lower() for part in target.parts]):
                continue
            with io.open(state_path, "rb") as handle:
                content = handle.read(32 * 1024 * 1024 + 1)
            if len(content) > 32 * 1024 * 1024:
                continue
            payload = json.loads(content)
        except (OSError, ValueError, TypeError):
            continue
        if (isinstance(payload, dict)
                and payload.get("schema_version") == "phx2_central_ath_v1"
                and isinstance(payload.get("mints"), dict)):
            return payload["mints"]
    return {}


def _overlay_central_ath(
    snapshot: CandidateSnapshot, central_mints: Dict[str, Dict[str, Any]]
) -> CandidateSnapshot:
    central = central_mints.get(snapshot.mint)
    if not isinstance(central, dict) or not _as_of(central, snapshot.ts_epoch, external=True):
        return snapshot
    if snapshot.extra.get("central_ath"):
        return snapshot  # the row's evidence is authoritative for that observation
    value = parse_number(central.get("ath_market_cap"))
    if value is None or value <= 0:
        return snapshot
    snapshot.ath_market_cap_usd = value
    snapshot.extra["central_ath"] = dict(central)
    snapshot.extra["ath_provenance"] = {
        "provider": central.get("ath_provider"),
        "observation_type": central.get("ath_observation_type"),
        "timestamp": central.get("ath_timestamp"),
        "status": central.get("ath_status"),
    }
    return snapshot


def normalize_record(record: Any, source_file: Optional[str] = None,
                     source_line: int = 0) -> Optional[CandidateSnapshot]:
    """Map one parsed JSONL record to a CandidateSnapshot, or None.

    Returns None when the record carries no usable mint or timestamp
    (e.g. an axiom fee record, a config echo, or malformed data).
    """
    if not isinstance(record, dict):
        return None
    containers = [
        record[name] for name in _NESTED_CONTAINERS
        if isinstance(record.get(name), dict)
    ]
    for container in list(containers):
        nested_ath = container.get("central_ath")
        if isinstance(nested_ath, dict):
            containers.insert(0, nested_ath)
    central_ath = next((value for value in (
        record.get("central_ath"),
        *(container.get("central_ath") for container in containers
          if isinstance(container, dict)),
    ) if isinstance(value, dict) and value.get("ath_market_cap") is not None), {})
    activation = record.get("activation")
    if not isinstance(activation, dict):
        activation = next((container.get("activation") for container in containers
                           if isinstance(container.get("activation"), dict)), {})
    if not activation and any(key in record for key in (
            "migration_baseline_status", "activation_multiplier", "activated_at_utc")):
        activation = {key: record.get(key) for key in (
            "migration_time_utc", "migration_market_cap_usd",
            "migration_market_cap_source", "migration_market_cap_observed_at_utc",
            "migration_market_cap_price", "migration_supply_at_observation",
            "migration_baseline_status", "migration_baseline_digest",
            "migration_baseline_digest_version", "activation_multiplier",
            "activation_target_market_cap_usd", "activated_at_utc",
            "activation_observation_source", "activation_current_market_cap_usd",
            "activation_observation_fresh", "activation_proven",
            "activation_evidence_source", "activation_evidence_market_cap_usd",
            "activation_evidence_event_at_utc", "activation_evidence_ingested_at_utc",
            "activation_evidence_digest", "activation_evidence_version",
            "activation_source_evidence_digest",
            "activation_observation_seal_digest",
            "activation_observation_seal_version",
            "activation_proof_digest", "activation_proof_version",
            "activation_evidence_kind", "activation_crossing_tick_digest",
            "activation_crossing_tick_blocked", "activation_latched",
            "activation_waiting_for_fresh_market",
            "activation_current_market_required_for_tier",
            "latest_market_readiness_state", "latest_market_readiness_reason")}
        activation["activation_state"] = record.get("status")
    contract_required = record.get("kind") in PRODUCER_INPUT_KINDS
    activation_required = bool(contract_required or
        activation
        or record.get("kind") == "BUILD30_CANDIDATE_RECHECK"
        or ("migration_time_utc" in record and "candidate_id" in record
            and "status" in record))

    mint = _first(record, containers, _MINT_KEYS)
    if not isinstance(mint, str) or not mint.strip():
        return None
    ts_epoch = parse_utc(_first(record, containers, _TS_KEYS))
    if ts_epoch is None:
        return None
    central_future = bool(central_ath and not _as_of(central_ath, ts_epoch))
    if central_future:
        central_ath = {}
    activation_as_of = _as_of(activation, ts_epoch)

    attempt = _last_attempt(record)
    reserve = _validated_reserve_telemetry(record, containers)
    price = parse_number(_first(record, containers, _PRICE_KEYS))
    if price is None:
        price = parse_number(attempt.get("price_value"))
    if price is None:
        price = parse_number(reserve.get("effective_reserve_price_usd"))
    market_cap = parse_number(_first(record, containers, _MC_KEYS))
    if market_cap is None:
        market_cap = parse_number(attempt.get("mc_value"))
    if market_cap is None:
        market_cap = parse_number(reserve.get("effective_reserve_market_cap_usd"))
    liquidity = parse_number(_first(record, containers, _LP_KEYS))
    if liquidity is None:
        liquidity = parse_number(attempt.get("lp_value"))
    if liquidity is None:
        liquidity = parse_number(reserve.get("effective_reserve_liquidity_usd"))

    drawdown = parse_pct_text(_first(record, containers, _DRAWDOWN_KEYS))
    if drawdown is None:
        drawdown = parse_pct_text(reserve.get("effective_reserve_drawdown_pct"))
    ath_market_cap = parse_number(central_ath.get("ath_market_cap"))
    if ath_market_cap is None:
        ath_market_cap = parse_money_text(_first(record, containers, _ATH_KEYS))
    if ath_market_cap is None:
        ath_market_cap = parse_money_text(
            reserve.get("effective_reserve_ath_market_cap_usd"))
    if central_future:
        ath_market_cap = None
        drawdown = None

    symbol = _first(record, containers, _SYMBOL_KEYS)
    if not isinstance(symbol, str) or not symbol.strip():
        symbol = None

    volume = parse_number(_first(record, containers, _VOLUME_KEYS))
    measured_volume = record.get("canonical_volume_5m")
    if isinstance(measured_volume, dict):
        # Both producer paths carry the same bounded, decoded five-minute
        # gross volume. Missing measurements remain unknown, never zero.
        valid_volume = (measured_volume.get("schema_version") == "phx2_canonical_swap_volume_v1"
            and measured_volume.get("status") == "VALID"
            and measured_volume.get("mint") == mint
            and measured_volume.get("window_seconds") == 300
            and type(measured_volume.get("sample_count")) is int
            and measured_volume["sample_count"] > 0)
        value = parse_number(measured_volume.get("gross_volume_usd")) if valid_volume else None
        volume = value if value is not None and value >= 0 else None

    snapshot = CandidateSnapshot(
        ts_epoch=ts_epoch,
        mint=mint.strip(),
        candidate_id=_first(record, containers, _CANDIDATE_ID_KEYS),
        symbol=symbol,
        price_usd=price if price is not None and price > 0 else None,
        market_cap_usd=(market_cap
                        if market_cap is not None and market_cap > 0 else None),
        liquidity_usd=(liquidity
                       if liquidity is not None and liquidity >= 0 else None),
        volume_usd=volume,
        supply=parse_number(_first(record, containers, _SUPPLY_KEYS)),
        tier=parse_tier(_first(record, containers, _TIER_KEYS)),
        drawdown_pct=drawdown,
        ath_market_cap_usd=ath_market_cap,
        score=parse_number(_first(record, containers, _SCORE_KEYS)),
        migration_ts_epoch=parse_utc(record.get("migration_time_utc")),
        source_kind=record.get("kind") if isinstance(record.get("kind"), str)
        else None,
        source_file=source_file,
        source_line=source_line,
        risk_label=parse_risk_label(_first(record, containers, _RISK_LABEL_KEYS)),
        risk_reasons=parse_risk_reasons(_first(record, containers, _RISK_REASON_KEYS)),
        fee_gate=(dict(record.get("fee_gate"))
                  if isinstance(record.get("fee_gate"), dict) else {}),
        lp_integrity=(dict(record.get("lp_integrity"))
                      if isinstance(record.get("lp_integrity"), dict) else {}),
        scam_policy=(dict(record.get("scam_policy"))
                     if isinstance(record.get("scam_policy"), dict) else {}),
        extra={
            "price_provenance": (
                "EFFECTIVE_PUMPSWAP_RESERVES"
                if price is not None
                and _first(record, containers, _PRICE_KEYS) is None
                and attempt.get("price_value") is None
                and reserve
                else "PRIMARY_MARKET"
            ),
            "pumpswap_reserve": reserve or None,
            "central_ath": central_ath or None,
            "ath_provenance": {
                "provider": central_ath.get("ath_provider"),
                "observation_type": central_ath.get("ath_observation_type"),
                "timestamp": central_ath.get("ath_timestamp"),
                "status": central_ath.get("ath_status"),
            } if central_ath else None,
            "activation": activation or None,
            "activation_required": activation_required,
            "activation_eligible": bool(
                (activation.get("activation_state") == "ACTIVE_DIP_WATCH"
                 or (record.get("kind") == "BUILD30_CANDIDATE_RECHECK"
                     and activation.get("activation_state") == "SENT_OK_COMMITTED"
                     and activation.get("activation_proof_valid") is True))
                and activation.get("activation_proof_valid") is True
                and activation.get("token_mint") == mint
                and activation.get("candidate_id") == _first(record, containers, _CANDIDATE_ID_KEYS)
                and activation.get("candidate_id")
                and activation.get("activation_proven")
                and activation.get("activation_observation_fresh")
                and activation.get("activation_latched")),
        },
    )
    if contract_required:
        quote_ts = parse_utc(_first(record, containers, (
            "price_observed_at_utc", "provider_timestamp_utc",
            "market_context_fetched_at_utc", "fetched_at_utc")))
        ttl = parse_number(_first(record, containers, ("market_price_ttl_seconds",)))
        ttl = min(ttl, 300.0) if ttl is not None and ttl > 0 else 300.0
        readiness = _first(record, containers, ("market_state",))
        price_fresh = _first(record, containers, ("price_fresh",))
        quote_usable = bool(snapshot.has_price and quote_ts is not None
                            and 0 <= ts_epoch - quote_ts <= ttl
                            and price_fresh is not False
                            and (readiness == "MARKET_READY" or price_fresh is True))
        fetched = _first(record, containers, ("market_context_fetched_at_utc", "fetched_at_utc"))
        mc_ts = parse_utc(_first(record, containers, ("market_cap_observed_at_utc",)) or fetched)
        lp_ts = parse_utc(_first(record, containers, ("liquidity_observed_at_utc",)) or fetched)
        lp_ttl = parse_number(_first(record, containers, ("market_overview_ttl_seconds",)))
        lp_ttl = min(lp_ttl, 300.0) if lp_ttl is not None and lp_ttl > 0 else 300.0
        market_ready = bool(readiness == "MARKET_READY"
            and snapshot.market_cap_usd is not None and snapshot.liquidity_usd is not None
            and mc_ts is not None and 0 <= ts_epoch - mc_ts <= ttl
            and lp_ts is not None and 0 <= ts_epoch - lp_ts <= lp_ttl
            and _first(record, containers, ("market_cap_fresh",)) is not False
            and _first(record, containers, ("liquidity_fresh",)) is not False)
        risk_ts = parse_utc(_first(record, containers, ("risk_assessed_at_utc",)))
        if risk_ts is None or not 0 <= ts_epoch - risk_ts <= 300:
            snapshot.risk_label = None
            snapshot.risk_reasons = []
        security_ts = parse_utc(record.get("security_assessed_at_utc"))
        security_current = bool(security_ts is not None
                                and 0 <= ts_epoch - security_ts <= 300)
        # Missing context is unknown, not implicit permission for entry or DCA.
        activation_ok = bool(snapshot.extra["activation_eligible"] and activation_as_of)
        coverage = record.get("pricing_coverage") or {}
        lease_until = parse_utc(coverage.get("lease_until_utc"))
        coverage_ok = bool(coverage.get("admitted") is True
                           and coverage.get("paper_feedback_ready") is True
                           and lease_until is not None and lease_until >= ts_epoch)
        security_ok = bool(security_current and snapshot.scam_policy.get("verdict")
                           in ("ALLOW", "ALLOW_WITH_SHADOW_WARNING"))
        continuation = record.get("paper_position_context")
        if not isinstance(continuation, dict):
            continuation = {}
        contexts = record.get("paper_position_contexts")
        contexts = contexts if isinstance(contexts, list) else [continuation]
        valid_contexts = []
        for context in contexts:
            if not isinstance(context, dict) or context.get("mint") != snapshot.mint:
                continue
            proof = context.get("activation")
            if (isinstance(proof, dict) and context.get("candidate_id")
                    and proof.get("token_mint") == snapshot.mint
                    and proof.get("candidate_id") == context["candidate_id"]
                    and proof.get("activation_proven") is True
                    and proof.get("activation_latched") is True
                    and proof.get("activation_proof_valid") is True
                    and _as_of(proof, ts_epoch)):
                valid_contexts.append(context)
        continuation_ok = bool(valid_contexts)
        current_exposure = bool(quote_usable and market_ready and security_ok
                                and snapshot.risk_label is not None and coverage_ok)
        snapshot.extra.update(
            contract_required=True, quote_observed_epoch=quote_ts,
            quote_usable=quote_usable, quote_ttl_seconds=ttl,
            activation_eligible=activation_ok,
            exposure_eligible=bool(current_exposure and activation_ok),
            dca_exposure_eligible=bool(current_exposure and continuation_ok),
            paper_position_context=continuation or None,
            paper_position_contexts=valid_contexts,
            pricing_coverage=coverage, market_state=readiness,
            security_current=security_current, risk_assessed_epoch=risk_ts,
            security_assessed_epoch=security_ts,
            market_cap_observed_epoch=mc_ts, liquidity_observed_epoch=lp_ts,
            liquidity_ttl_seconds=lp_ttl, market_ready_for_exposure=market_ready,
            ath_as_of_valid=not central_future,
        )
    return snapshot


# ---------------------------------------------------------------------------
# File discovery + replay stream
# ---------------------------------------------------------------------------


def discover_input_files(paths: Iterable[str]) -> List[str]:
    """Expand files / directories / glob patterns into a sorted file list.

    Producer-internal bookkeeping basenames (``EXCLUDED_INPUT_BASENAMES``) are
    dropped when discovered via a directory/glob expansion; a file the operator
    names EXPLICITLY is always kept (explicit wins).
    """
    found: List[str] = []

    def _keep(path: Path) -> bool:
        return path.name.lower() not in EXCLUDED_INPUT_BASENAMES

    for raw in paths:
        text = str(raw)
        path = Path(text)
        if path.is_file():
            found.append(str(path))     # explicit file: operator asked for it
        elif path.is_dir():
            found.extend(str(p) for p in path.rglob("*.jsonl") if _keep(p))
        elif any(ch in text for ch in "*?["):
            for hit in _glob.glob(text, recursive=True):
                hit_path = Path(hit)
                if hit_path.is_file():
                    if _keep(hit_path):
                        found.append(str(hit_path))
                elif hit_path.is_dir():
                    found.extend(str(p) for p in hit_path.rglob("*.jsonl")
                                 if _keep(p))
    # Dedupe while keeping deterministic (sorted) order.
    return sorted(set(os.path.normpath(p) for p in found))


def load_snapshots(paths: Iterable[str],
                   include_kinds: Optional[Iterable[str]] = None,
                   ) -> Tuple[List[CandidateSnapshot], List[Dict[str, Any]]]:
    """Load + normalize + time-sort snapshots from JSONL inputs.

    Returns ``(snapshots, errors)``; errors carry file/line/problem text for
    the error ledger and never raise.
    """
    kinds = set(include_kinds) if include_kinds else None
    snapshots: List[CandidateSnapshot] = []
    errors: List[Dict[str, Any]] = []
    for file_path in discover_input_files(paths):
        central_mints = _load_central_ath_for_input(file_path)
        try:
            with io.open(file_path, "rb") as handle:
                raw = handle.read()
        except OSError as exc:
            errors.append({
                "kind": "READ_ERROR",
                "file": file_path,
                "line": 0,
                "error": str(exc),
            })
            continue
        if not raw:
            continue
        # A final line with no terminating newline can be a partial write (the
        # producer is mid-append): a parse failure on THAT line means
        # "incomplete, retry when complete", not a hard PARSE_ERROR. A
        # newline-terminated line that fails to parse is a genuinely malformed
        # COMPLETE line and still errors, exactly as before.
        trailing_partial = not raw.endswith((b"\n", b"\r"))
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        for line_no, line in enumerate(lines, start=1):
            is_last = line_no == len(lines)
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                if is_last and trailing_partial:
                    continue
                errors.append({
                    "kind": "PARSE_ERROR",
                    "file": file_path,
                    "line": line_no,
                    "error": str(exc),
                })
                continue
            snap = normalize_record(record, file_path, line_no)
            if snap is None:
                continue
            if kinds is not None and snap.source_kind not in kinds:
                continue
            snap = _overlay_central_ath(snap, central_mints)
            snapshots.append(snap)
    snapshots.sort(key=lambda s: s.sort_key())
    return snapshots, errors


class TailingSnapshotSource:
    """Incremental reader for live paper mode.

    Tracks byte offsets per file and yields only newly appended records on
    each ``poll()``. Read-only on the input files; safe to point at a
    directory another process is appending to.
    """

    MAX_INPUT_FILES = 4096
    MAX_POLL_FILES = 64
    MAX_POLL_BYTES = 4 * 1024 * 1024
    MAX_POLL_RECORDS = 1024

    def __init__(self, paths: Iterable[str],
                 include_kinds: Optional[Iterable[str]] = None,
                 producer_streams_only: bool = False,
                 allow_input_rollover: bool = False) -> None:
        self._paths = sorted(set(os.path.normcase(os.path.abspath(str(p))) for p in paths))
        if producer_streams_only and not 1 <= len(self._paths) <= 16:
            raise ValueError("PAPER_INPUT_SELECTION_INVALID")
        self._producer_only = producer_streams_only
        self._allow_input_rollover = allow_input_rollover
        self._kinds = (set(PRODUCER_INPUT_KINDS) if producer_streams_only else
                       set(include_kinds) if include_kinds else None)
        self._offsets: Dict[str, int] = {}
        self._files: Dict[str, Dict[str, Any]] = {}
        self._cursor: str = ""

    def checkpoint_state(self) -> Dict[str, Any]:
        return {"offsets": self.offsets, "files": dict(self._files),
                "selection": self._selection(), "cursor": self._cursor}

    def _selection(self) -> Dict[str, Any]:
        return {"paths": self._paths, "producer_streams_only": self._producer_only,
                "include_kinds": sorted(self._kinds) if self._kinds is not None else None}

    def restore_checkpoint(self, payload: Dict[str, Any]) -> None:
        selected = self._selection()
        prior = payload.get("selection")
        if prior is not None and prior != selected:
            # Explicit rollover adds a new producer run while retaining every
            # prior input and its unread suffix. Removing/replacing a root is
            # a separate migration, never an implicit reset to byte zero.
            rollover = (self._allow_input_rollover and isinstance(prior, dict)
                and prior.get("producer_streams_only") == selected["producer_streams_only"]
                and prior.get("include_kinds") == selected["include_kinds"]
                and isinstance(prior.get("paths"), list)
                and set(prior["paths"]) < set(selected["paths"]))
            if not rollover:
                raise ValueError("PAPER_INPUT_SELECTION_MISMATCH")
        elif (prior is None and self._producer_only
              and (payload.get("offsets") or payload.get("files"))):
            raise ValueError("PAPER_INPUT_SELECTION_MISSING")
        self.set_offsets(payload.get("offsets", {}))
        self._files = dict(payload.get("files", {}))
        if max(len(self._offsets), len(self._files)) > self.MAX_INPUT_FILES:
            raise ValueError("PAPER_INPUT_FILE_LIMIT_EXCEEDED")
        self._cursor = str(payload.get("cursor") or "")

    def _input_files(self) -> List[str]:
        if not self._producer_only:
            return discover_input_files(self._paths)
        def direct_candidates(directory):
            if directory.is_dir():
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.name.endswith(".jsonl"):
                            yield Path(entry.path)
        found = []
        for raw in self._paths:
            path = Path(raw)
            resolved = path.resolve()
            if (path.is_symlink() or path.is_junction()
                    or "phoenix_bot" in [p.lower() for p in resolved.parts]):
                raise ValueError("PAPER_INPUT_PATH_REFUSED")
            if path.is_dir():
                root = resolved
                child = path / "candidates"
                if child.is_symlink() or child.is_junction() or not child.resolve().is_relative_to(root):
                    raise ValueError("PAPER_INPUT_PATH_REFUSED")
                candidates = itertools.chain([path / "pricing_tail.jsonl"], direct_candidates(child))
            else:
                candidates = [path]
                root = resolved.parent
            for candidate in candidates:
                target = candidate.resolve()
                if (candidate.is_symlink() or candidate.is_junction()
                        or not target.is_relative_to(root)
                        or "phoenix_bot" in [p.lower() for p in target.parts]):
                    raise ValueError("PAPER_INPUT_PATH_REFUSED")
                if not candidate.is_file():
                    continue
                if candidate.name != "pricing_tail.jsonl" and not (
                        candidate.parent.name == "candidates" and candidate.suffix == ".jsonl"):
                    raise ValueError("PAPER_INPUT_NOT_PRODUCER_STREAM")
                if candidate.is_symlink() or "phoenix_bot" in [p.lower() for p in candidate.parts]:
                    raise ValueError("PAPER_INPUT_PATH_REFUSED")
                found.append(str(candidate.resolve()))
                if len(found) > self.MAX_INPUT_FILES:
                    raise ValueError("PAPER_INPUT_FILE_LIMIT_EXCEEDED")
        return sorted(set(found))

    @property
    def offsets(self) -> Dict[str, int]:
        """Per-file byte offsets consumed so far (checkpointable)."""
        return dict(self._offsets)

    def set_offsets(self, offsets: Dict[str, int]) -> None:
        """Restore previously checkpointed offsets so a restarted live run
        does not reprocess already-consumed records."""
        self._offsets = {
            str(path): int(offset)
            for path, offset in (offsets or {}).items()
            if isinstance(offset, (int, float)) and int(offset) >= 0
        }

    def poll(self) -> Tuple[List[CandidateSnapshot], List[Dict[str, Any]]]:
        snapshots: List[CandidateSnapshot] = []
        errors: List[Dict[str, Any]] = []
        input_files = self._input_files()
        if self._producer_only and set(self._files) - set(input_files):
            raise ValueError("PAPER_CHECKPOINTED_INPUT_MISSING")
        if len(input_files) > self.MAX_INPUT_FILES:
            raise ValueError("PAPER_INPUT_FILE_LIMIT_EXCEEDED")
        priority = [path for path in input_files if Path(path).name == "pricing_tail.jsonl"
                    and Path(path).parent.name != "candidates"]
        if len(priority) >= self.MAX_POLL_FILES:
            raise ValueError("PAPER_PRIORITY_STREAM_LIMIT_EXCEEDED")
        candidates = [path for path in input_files if path not in priority]
        start = bisect.bisect_right(candidates, self._cursor)
        ordered = priority + (candidates[start:] + candidates[:start])[:self.MAX_POLL_FILES - len(priority)]
        # Open-position quotes get service every poll, independent of historical
        # candidate count. Reserve half the aggregate budget across tail streams;
        # unused tail budget remains available to the fair candidate rotation.
        tail_bytes = max(1, self.MAX_POLL_BYTES // 2 // max(1, len(priority)))
        tail_records = max(1, self.MAX_POLL_RECORDS // 2 // max(1, len(priority)))
        remaining_bytes = self.MAX_POLL_BYTES
        remaining_records = self.MAX_POLL_RECORDS
        for file_path in ordered:
            if remaining_bytes <= 0 or remaining_records <= 0:
                break
            is_priority = file_path in priority
            if not is_priority:
                self._cursor = file_path
            file_byte_limit = min(remaining_bytes, tail_bytes) if is_priority else remaining_bytes
            file_record_limit = min(remaining_records, tail_records) if is_priority else remaining_records
            row_limit = (tail_bytes if is_priority else
                         self.MAX_POLL_BYTES // 2 if priority else self.MAX_POLL_BYTES)
            file_bytes_left, file_records_left = file_byte_limit, file_record_limit
            central_mints = ({} if self._producer_only else _load_central_ath_for_input(file_path))
            offset = self._offsets.get(file_path, 0)
            try:
                with io.open(file_path, "rb") as handle:
                    stat = os.fstat(handle.fileno())
                    prior = self._files.get(file_path)
                    anchor_size = int(prior["anchor_size"]) if prior else min(stat.st_size, 256)
                    anchor = hashlib.sha256(handle.read(anchor_size)).hexdigest()
                    identity = {"device": stat.st_dev, "inode": stat.st_ino,
                                "anchor_size": anchor_size, "anchor": anchor}
                    if stat.st_size < offset or (prior is not None and prior != identity):
                        raise ValueError("PAPER_INPUT_REPLACED_OR_TRUNCATED")
                    if stat.st_size <= offset:
                        continue
                    handle.seek(offset)
                    lines = []
                    consumed_bytes = 0
                    while file_records_left > 0 and file_bytes_left > 0:
                        read_budget = file_bytes_left
                        raw_line = handle.readline(min(read_budget, row_limit + 1))
                        if not raw_line:
                            break
                        remaining_bytes -= len(raw_line)
                        file_bytes_left -= len(raw_line)
                        if len(raw_line) > row_limit:
                            raise ValueError("PAPER_INPUT_LINE_TOO_LARGE")
                        if not raw_line.endswith(b"\n"):
                            if len(raw_line) >= row_limit:
                                raise ValueError("PAPER_INPUT_LINE_TOO_LARGE")
                            break  # defer this whole line, keeping its byte offset
                        lines.append(raw_line)
                        consumed_bytes += len(raw_line)
                        remaining_records -= 1
                        file_records_left -= 1
                # Consume only whole newline-terminated lines; a partial
                # trailing line (the producer is mid-append) is left
                # unconsumed and re-read once complete on the next poll.
                # The offset is tracked on the RAW bytes so it always lands on
                # a true line boundary: a text-mode read translates CRLF -> LF
                # and re-encoding under-counts each line ending by one byte,
                # so the offset drifts and the next seek starts mid-line,
                # feeding a fragment to json.loads -> spurious PARSE_ERRORs
                # ("Expecting value" / "Extra data") that clear on a later poll.
                if not consumed_bytes:
                    continue
                self._files[file_path] = identity
                self._offsets[file_path] = offset + consumed_bytes
                for line_no, raw_line in enumerate(lines, start=1):
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        errors.append({
                            "kind": "PARSE_ERROR",
                            "file": file_path,
                            "line": line_no,
                            "error": str(exc),
                        })
                        continue
                    snap = normalize_record(record, file_path, line_no)
                    if snap is None:
                        continue
                    if self._kinds is not None and snap.source_kind not in self._kinds:
                        continue
                    snap = _overlay_central_ath(snap, central_mints)
                    snap.extra["source_record_digest"] = hashlib.sha256(
                        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                    snapshots.append(snap)
            except OSError as exc:
                errors.append({
                    "kind": "READ_ERROR",
                    "file": file_path,
                    "line": 0,
                    "error": str(exc),
                })
        snapshots.sort(key=lambda s: s.sort_key())
        return snapshots, errors


__all__ = [
    "EXCLUDED_INPUT_BASENAMES",
    "normalize_record",
    "discover_input_files",
    "load_snapshots",
    "TailingSnapshotSource",
]
