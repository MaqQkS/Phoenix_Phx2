"""production_live_lp_verify.py — OBSERVE-ONLY liquidity-pool verifier (pure, fake/replay-first).

Consumes LP/pool events (from FAKE/replay fixtures now; a dedicated SECOND Chainstack Yellowstone
"LP verification stream" later) and emits an LP-verification verdict whose purpose is to distinguish
REAL reserve movement from wash/fake volume + LP rug/drain. It is:
  * PURE + TOTAL + DETERMINISTIC — never raises (fails CLOSED to UNKNOWN), no I/O, no clock, no network.
  * OBSERVE-ONLY — it NEVER blocks a send, NEVER touches the durable ledger, NEVER imports the transport
    or the Axiom decoder, and does NOT change PHX2_BASELINE_ELIGIBILITY or the runner LP floor.
  * NOT WIRED into the live send path. This stage only proves the model + artifacts offline.

Signal vs Axiom fees: the DBX reconciliation proved decoded Solana tx ``meta.fee`` (~0.0108 SOL) is NOT
the Axiom UI lifetime figure (~9.943 SOL, ~922x off), so Axiom fees are kept as DEBUG/telemetry only.
Real pool-reserve movement is a far better conviction/anti-wash filter — this module models that.
"""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, List, Optional, Tuple

_SELF = str(Path(__file__).resolve().parent)
if _SELF not in sys.path:
    sys.path.insert(0, _SELF)

import production_live_lp_verify_models as m   # noqa: E402  (sibling model, stdlib-only)

_LAMPORTS_PER_SOL = Decimal(1_000_000_000)
_RATIO_Q = Decimal("0.0001")
_SCORE_Q = Decimal("0.001")

# Observe-only artifact SOURCES (which feed produced the LP verdict). The real Chainstack second-Yellowstone
# "LP verification stream" source is RESERVED and intentionally NOT used yet (this stage has no live stream).
LP_SOURCE_NO_STREAM = "NO_LP_STREAM_EVENTS"
LP_SOURCE_FAKE_REPLAY = "FAKE_REPLAY_FIXTURE"
LP_SOURCE_LIVE_STREAM = "CHAINSTACK_YELLOWSTONE_LP_STREAM"   # reserved; NOT wired this stage
LP_OBSERVE_ARTIFACT_KIND = "PRODUCTION_LIVE_LP_VERIFY_OBSERVE"


def _sol_text(lamports: int, places: int = 9) -> str:
    q = (Decimal(int(lamports)) / _LAMPORTS_PER_SOL).quantize(Decimal(1).scaleb(-places))
    return format(q, "f")


def _sol_2dp_signed(sol_text: str) -> str:
    try:
        q = Decimal(sol_text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        q = Decimal("0.00")
    return format(q, "+.2f")


def _as_decimal_or_none(v: Any) -> Optional[Decimal]:
    if isinstance(v, bool):
        return None
    if isinstance(v, Decimal):
        return v if v.is_finite() else None
    return None


def _seq(x: Any) -> Tuple[Any, ...]:
    return tuple(x) if x else ()


def _evidence_window_seconds(swaps, snaps, liq) -> float:
    ts: List[float] = []
    for s in swaps:
        ts.append(float(s.timestamp_s))
    for s in snaps:
        ts.append(float(s.timestamp_s))
    for e in liq:
        ts.append(float(e.timestamp_s))
    if len(ts) < 2:
        return 0.0
    return round(max(ts) - min(ts), 3)


def _stability_score(*, swaps, snaps, liq, ratio: Decimal, below_floor: bool) -> Decimal:
    """Deterministic 0..1 LP-stability score. 1.0 = healthy/stable; penalize reserve drawdown, net
    liquidity removal, wash-like churn (many direction flips with low movement ratio), and below-floor LP."""
    penalty = Decimal(0)
    if snaps:
        sols = [s.effective_quote_reserves for s in snaps]
        peak = max(sols)
        last = sols[-1]
        if peak > 0 and last < peak:
            penalty += (Decimal(peak - last) / Decimal(peak))          # drawdown fraction 0..1
    removed = sum(e.sol_amount_lamports for e in liq if e.kind == m.LP_EVENT_REMOVE)
    added = sum(e.sol_amount_lamports for e in liq if e.kind == m.LP_EVENT_ADD)
    if (removed + added) > 0:
        penalty += Decimal("0.5") * (Decimal(removed) / Decimal(removed + added))
    n = len(swaps)
    if n > 1 and ratio < Decimal("0.15"):
        flips = 0
        for i in range(1, n):
            a = swaps[i - 1].sol_delta_lamports
            b = swaps[i].sol_delta_lamports
            if (a > 0 > b) or (a < 0 < b):
                flips += 1
        penalty += Decimal("0.4") * (Decimal(flips) / Decimal(n - 1))
    if below_floor:
        penalty += Decimal("0.3")
    score = Decimal(1) - penalty
    if score < 0:
        score = Decimal(0)
    if score > 1:
        score = Decimal(1)
    return score.quantize(_SCORE_Q)


def _result(*, status, reason, wash, pool_delta_sol_lamports, pool_delta_token, observed_swap_count,
            net_sol_lamports, gross_sol_lamports, ratio, score, window_s, pool_found, inp, notes,
            reserve_snapshot=None):
    return m.LpVerifyResult(
        lp_verify_status=status, lp_verify_reason=reason, wash_risk=wash,
        pool_delta_sol=_sol_text(pool_delta_sol_lamports),
        pool_delta_token=str(int(pool_delta_token)),
        observed_swap_count=int(observed_swap_count),
        net_sol_flow=_sol_text(net_sol_lamports), gross_sol_flow=_sol_text(gross_sol_lamports),
        reserve_movement_ratio=format(ratio.quantize(_RATIO_Q), "f"),
        lp_stability_score=format(score.quantize(_SCORE_Q), "f"),
        evidence_window_seconds=float(window_s), pool_found=bool(pool_found), observe_only=True,
        lp_floor_usd=format(inp.lp_floor_usd, "f"), candidate_mint=inp.candidate_mint,
        pool_protocol=(inp.pool_protocol if isinstance(inp.pool_protocol, str) else None),
        pumpswap_reserve=reserve_snapshot,
        notes=tuple(notes))


def verify_lp(inp: "m.LpVerifyInput", config: "Optional[m.LpVerifyConfig]" = None) -> "m.LpVerifyResult":
    """Pure observe-only LP verdict. Never raises; on any malformed input fails CLOSED to UNKNOWN."""
    try:
        cfg = config or m.LpVerifyConfig()
        swaps = _seq(inp.swaps)
        snaps = _seq(inp.reserve_snapshots)
        liq = _seq(inp.liquidity_events)

        observed_swap_count = len(swaps)
        gross = sum(abs(s.sol_delta_lamports) for s in swaps)
        net = sum(s.sol_delta_lamports for s in swaps)
        net_token = sum(s.token_delta_base_units for s in swaps)

        if len(snaps) >= 2:
            pool_delta_sol = (
                snaps[-1].effective_quote_reserves - snaps[0].effective_quote_reserves)
            pool_delta_token = snaps[-1].base_reserves - snaps[0].base_reserves
        else:
            pool_delta_sol = net
            pool_delta_token = net_token

        if gross > 0:
            ratio = (Decimal(abs(pool_delta_sol)) / Decimal(gross))
        else:
            ratio = Decimal(1) if pool_delta_sol != 0 else Decimal(0)
        if ratio < 0:
            ratio = Decimal(0)

        window_s = _evidence_window_seconds(swaps, snaps, liq)
        pool_found = bool(inp.pool_address) or bool(snaps) or bool(swaps)

        cur = _as_decimal_or_none(inp.current_liquidity_usd)
        floor = inp.lp_floor_usd if isinstance(inp.lp_floor_usd, Decimal) else m.LP_FLOOR_USD_DEFAULT
        below_floor = (cur is not None and cur < floor)
        lp_above_floor = (cur is None) or (cur >= floor)

        score = _stability_score(swaps=swaps, snaps=snaps, liq=liq, ratio=ratio, below_floor=below_floor)

        common = dict(pool_delta_sol_lamports=pool_delta_sol, pool_delta_token=pool_delta_token,
                      observed_swap_count=observed_swap_count, net_sol_lamports=net,
                      gross_sol_lamports=gross, ratio=ratio, score=score, window_s=window_s, inp=inp)
        common["reserve_snapshot"] = snaps[-1].to_dict() if snaps else None

        # 1) pool not found -> observe-only UNKNOWN (NOT a hard blocker this stage).
        if not pool_found:
            return _result(status=m.LP_VERIFY_UNKNOWN, reason=m.POOL_NOT_FOUND, wash=m.WASH_RISK_UNKNOWN,
                           pool_found=False, notes=("no_pool_addr_no_events",), **common)

        # 2) insufficient evidence -> UNKNOWN.
        total_events = observed_swap_count + len(snaps) + len(liq)
        if total_events < cfg.min_events or (observed_swap_count == 0 and len(snaps) < 2 and not liq):
            return _result(status=m.LP_VERIFY_UNKNOWN, reason=m.INSUFFICIENT_EVENTS,
                           wash=m.WASH_RISK_UNKNOWN, pool_found=True,
                           notes=(f"events={total_events}", f"min={cfg.min_events}"), **common)

        # 3) LP rug / drain -> FAIL.
        removed = sum(e.sol_amount_lamports for e in liq if e.kind == m.LP_EVENT_REMOVE)
        added = sum(e.sol_amount_lamports for e in liq if e.kind == m.LP_EVENT_ADD)
        drain_by_remove = removed > 0 and removed >= added and removed > gross
        drain_by_reserve = False
        if snaps:
            peak = max(s.effective_quote_reserves for s in snaps)
            last = snaps[-1].effective_quote_reserves
            if peak > 0 and (Decimal(peak - last) / Decimal(peak)) >= cfg.drain_fraction_fail:
                drain_by_reserve = True
        if drain_by_remove or drain_by_reserve:
            note = "drain_by_remove" if drain_by_remove else "drain_by_reserve"
            return _result(status=m.LP_VERIFY_FAIL, reason=m.LP_REMOVED_OR_DRAINING,
                           wash=m.WASH_RISK_HIGH, pool_found=True, notes=(note,), **common)

        high_gross = gross >= cfg.high_gross_sol_lamports

        # 4) wash: high churn, low net reserve movement vs volume.
        if high_gross and ratio < cfg.wash_reserve_ratio_fail:
            return _result(status=m.LP_VERIFY_FAIL, reason=m.WASH_PATTERN_SUSPECTED,
                           wash=m.WASH_RISK_HIGH, pool_found=True,
                           notes=("high_gross", "ratio_below_fail"), **common)
        if ratio < cfg.wash_reserve_ratio_warn:
            return _result(status=m.LP_VERIFY_WARN, reason=m.LOW_RESERVE_MOVEMENT_VS_VOLUME,
                           wash=(m.WASH_RISK_HIGH if high_gross else m.WASH_RISK_MEDIUM), pool_found=True,
                           notes=("ratio_below_warn",), **common)

        # 5) unstable pool state -> WARN.
        if score < cfg.stability_unstable_max:
            return _result(status=m.LP_VERIFY_WARN, reason=m.UNSTABLE_POOL_STATE,
                           wash=m.WASH_RISK_MEDIUM, pool_found=True, notes=("low_stability",), **common)

        # 6) real reserve movement + LP above floor + stable -> PASS.
        if ratio >= cfg.real_movement_ratio_min and lp_above_floor:
            return _result(status=m.LP_VERIFY_PASS, reason=m.REAL_RESERVE_MOVEMENT,
                           wash=m.WASH_RISK_LOW, pool_found=True,
                           notes=("real_movement", "above_floor" if cur is not None else "floor_unknown"),
                           **common)

        # conservative fallback (e.g. ratio in the mid band, or below-floor static LP).
        return _result(status=m.LP_VERIFY_WARN, reason=m.UNSTABLE_POOL_STATE,
                       wash=m.WASH_RISK_MEDIUM, pool_found=True,
                       notes=("below_floor" if below_floor else "mid_band",), **common)
    except Exception as exc:   # fail CLOSED — never raise into the caller
        try:
            mint = inp.candidate_mint if isinstance(getattr(inp, "candidate_mint", None), str) else "?"
            floor_txt = format(inp.lp_floor_usd, "f") if isinstance(getattr(inp, "lp_floor_usd", None), Decimal) \
                else format(m.LP_FLOOR_USD_DEFAULT, "f")
        except Exception:
            mint, floor_txt = "?", format(m.LP_FLOOR_USD_DEFAULT, "f")
        return m.LpVerifyResult(
            lp_verify_status=m.LP_VERIFY_UNKNOWN, lp_verify_reason=m.INSUFFICIENT_EVENTS,
            wash_risk=m.WASH_RISK_UNKNOWN, pool_delta_sol="0.000000000", pool_delta_token="0",
            observed_swap_count=0, net_sol_flow="0.000000000", gross_sol_flow="0.000000000",
            reserve_movement_ratio="0.0000", lp_stability_score="0.000", evidence_window_seconds=0.0,
            pool_found=False, observe_only=True, lp_floor_usd=floor_txt, candidate_mint=mint,
            pool_protocol=None, notes=("failed_closed", type(exc).__name__))


def format_lp_verify_line_from_block(block: dict) -> str:
    """OBSERVE-ONLY LP Verify display line built from an lp_verify dict — either an
    ``LpVerifyResult.to_dict()`` OR a ``build_lp_verify_observe_artifact(...)`` block (both carry the same
    ``lp_verify_*`` keys). PASS shows the pool delta + swap count; every other status shows the reason (so
    it NEVER implies "verified" unless PASS). Redaction-safe (closed-set tokens + public numbers); pure."""
    b = block or {}
    status = b.get("lp_verify_status", m.LP_VERIFY_UNKNOWN)
    wash = b.get("wash_risk", m.WASH_RISK_UNKNOWN)
    short = str(status).replace("LP_VERIFY_", "")
    if status == m.LP_VERIFY_PASS:
        return ("LP Verify: PASS · Wash Risk: %s · Pool Δ: %s SOL · Swaps: %s"
                % (wash, _sol_2dp_signed(str(b.get("pool_delta_sol", "0"))), b.get("observed_swap_count", 0)))
    return ("LP Verify: %s · Wash Risk: %s · Reason: %s"
            % (short, wash, b.get("lp_verify_reason", m.INSUFFICIENT_EVENTS)))


def format_lp_verify_line(result: "m.LpVerifyResult") -> str:
    """OBSERVE-ONLY Discord display line for an ``LpVerifyResult`` (delegates to
    ``format_lp_verify_line_from_block``). Example:
    ``LP Verify: PASS · Wash Risk: LOW · Pool Δ: +3.42 SOL · Swaps: 28``."""
    return format_lp_verify_line_from_block(result.to_dict())


def build_lp_verify_observe_artifact(result: "Optional[m.LpVerifyResult]" = None, *,
                                     source: "Optional[str]" = None, enabled: bool = True) -> dict:
    """OBSERVE-ONLY LP-verify artifact block for embedding in candidate/recheck artifacts. It NEVER gates a
    send (``lp_verify_used_for_blocking`` is always False) and changes NO eligibility / LP-floor / routing.
    With ``result`` None — no second-stream events, the LIVE default this stage — it returns the
    NO_LP_STREAM_EVENTS placeholder: UNKNOWN / INSUFFICIENT_EVENTS / wash UNKNOWN with zeroed metrics.
    Redaction-safe (closed-set tokens + public numbers only)."""
    if result is None:
        return {
            "kind": LP_OBSERVE_ARTIFACT_KIND,
            "lp_verify_enabled": bool(enabled),
            "lp_verify_observe_only": True,
            "lp_verify_used_for_blocking": False,
            "lp_verify_source": source or LP_SOURCE_NO_STREAM,
            "lp_verify_status": m.LP_VERIFY_UNKNOWN,
            "lp_verify_reason": m.INSUFFICIENT_EVENTS,
            "wash_risk": m.WASH_RISK_UNKNOWN,
            "pool_delta_sol": "0.000000000",
            "pool_delta_token": "0",
            "observed_swap_count": 0,
            "net_sol_flow": "0.000000000",
            "gross_sol_flow": "0.000000000",
            "reserve_movement_ratio": "0.0000",
            "lp_stability_score": "0.000",
            "evidence_window_seconds": 0.0,
        }
    d = result.to_dict()
    return {
        "kind": LP_OBSERVE_ARTIFACT_KIND,
        "lp_verify_enabled": bool(enabled),
        "lp_verify_observe_only": True,
        "lp_verify_used_for_blocking": False,
        "lp_verify_source": source or LP_SOURCE_FAKE_REPLAY,
        "lp_verify_status": d["lp_verify_status"],
        "lp_verify_reason": d["lp_verify_reason"],
        "wash_risk": d["wash_risk"],
        "pool_delta_sol": d["pool_delta_sol"],
        "pool_delta_token": d["pool_delta_token"],
        "observed_swap_count": d["observed_swap_count"],
        "net_sol_flow": d["net_sol_flow"],
        "gross_sol_flow": d["gross_sol_flow"],
        "reserve_movement_ratio": d["reserve_movement_ratio"],
        "lp_stability_score": d["lp_stability_score"],
        "evidence_window_seconds": d["evidence_window_seconds"],
    }


__all__ = ("verify_lp", "format_lp_verify_line", "format_lp_verify_line_from_block",
           "build_lp_verify_observe_artifact", "LP_SOURCE_NO_STREAM", "LP_SOURCE_FAKE_REPLAY",
           "LP_SOURCE_LIVE_STREAM", "LP_OBSERVE_ARTIFACT_KIND")
