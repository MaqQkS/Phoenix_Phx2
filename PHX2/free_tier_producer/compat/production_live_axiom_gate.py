"""production_live_axiom_gate.py — Axiom router/fee quality gate (PRE-reserve, PRE-send).

OUT-OF-REPO operator glue. Pure stdlib, NO network here (the data source is injected; the real
network source lives in ``production_live_axiom_source.py``).

WHERE THIS RUNS:
    discover/seed -> watchlist -> [THIS AXIOM GATE] -> (only Axiom-PASSED) -> committed
    run_cap1_candidates (compose+dedupe RESERVE -> Stage30_11_16 guard -> Stage28.9/28.4 send) ->
    durable JsonlPingDedupeLedger. The gate runs BEFORE any reserve and BEFORE any Discord send; an
    Axiom-FAILED candidate is never passed on, so it can neither reserve a ledger line nor send.

GATE SEMANTICS (Paul's blueprint, 2026-06-21): a candidate PASSES iff a RECENT SUCCESSFUL Axiom-
ROUTED swap for the candidate mint exists through one of the TWO ACTIVE Axiom router programs AND
observed fee metrics (total + priority lamports) are available. Deprecated Axiom routers are NEVER
pass evidence. We deliberately DO NOT claim "Axiom platform fee paid" — we report only what the
decoded transaction proves: an Axiom-routed swap was detected, the router program, tx fee lamports,
priority/base fee lamports, inner fee-program evidence, and success/failure.

NO faked Axiom data: the source returns real decoded evidence or fails closed. With no RPC source
wired, the gate fails closed (SOURCE_UNAVAILABLE) and the runner sends nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

try:
    from typing import Protocol, runtime_checkable
except Exception:  # pragma: no cover
    Protocol = object  # type: ignore

    def runtime_checkable(x):  # type: ignore
        return x


# --------------------------------------------------------------------------- Axiom router programs

# ACTIVE (INCLUDE) — the ONLY programs that can produce a PASS verdict.
# Codex Blocker 5 (2026-06-21): the active allowlist must contain ONLY committed/canonical router ids.
# The committed Stage 24 constants (PHX2/stage24/constants.py ACTIVE_AXIOM_ROUTER_PROGRAM_IDS) are the
# canonical source of truth: "Trading Program 1" spells "...Qz3Umzpgb..." and FLASHX8 as below. Paul's
# OCR/blueprint screenshot spells "...Qz3UmzMpgb..." (one extra "M"); that variant is NOT committed and
# NOT independently confirmed on-chain, so it is NOT admitted as an active router (admitting an
# uncommitted public key broadens the allowlist without provenance). It is retained only as a named
# constant so the selftest can prove it does NOT pass.
AXIOM_ROUTER_TRADING_PROGRAM_1 = "AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzpgbMG6"            # committed canonical
AXIOM_ROUTER_TRADING_PROGRAM_1_BLUEPRINT = "AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzMpgbMG6"  # uncommitted OCR variant — NOT active
AXIOM_ROUTER_AXIOM_TRADE = "FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9"
AXIOM_ACTIVE_ROUTER_PROGRAMS: Dict[str, str] = {
    AXIOM_ROUTER_TRADING_PROGRAM_1: "Trading Program 1",
    AXIOM_ROUTER_AXIOM_TRADE: "Axiom Trade",
}

# DEPRECATED (EXCLUDE) — never pass evidence; presence only sets the informational
# deprecated_router_seen flag. Canonical ids are the committed Stage 24 DEPRECATED_AXIOM_ROUTER_
# PROGRAM_IDS; OCR variants of "Trading Program 2" are kept as harmless extra aliases.
AXIOM_DEPRECATED_ROUTER_CANONICAL = (
    "AxiomxSitivYjPjKgJ9XSrdhsydtZssk7TEDam3PxKcC",   # committed canonical "Trading Program 2"
    "Axiom3a2w1UbMt2SMgqSvRiuJFTPusDhwKamNgPTeNQ9",   # committed canonical "mostly dead"
)
AXIOM_DEPRECATED_ROUTER_PROGRAMS = frozenset(AXIOM_DEPRECATED_ROUTER_CANONICAL + (
    "AxiomxSitiyXyPjKgJ9XSrdhsydtZsskZTEDam3PxKcC",   # screenshot OCR variant
    "AxiomxSjtivXyPjkgJ9XSrdhsydtZsskZTEDam3PxKcC",   # message OCR variant
))


def router_label(program_id: Optional[str]) -> Optional[str]:
    if not program_id:
        return None
    return AXIOM_ACTIVE_ROUTER_PROGRAMS.get(program_id)


def is_active_axiom_router(program_id: Optional[str]) -> bool:
    return bool(program_id) and program_id in AXIOM_ACTIVE_ROUTER_PROGRAMS


def is_deprecated_axiom_router(program_id: Optional[str]) -> bool:
    return bool(program_id) and program_id in AXIOM_DEPRECATED_ROUTER_PROGRAMS


# --------------------------------------------------------------------------- closed-set statuses

AXIOM_GATE_PASSED = "PASSED"
AXIOM_GATE_FAILED = "FAILED"
AXIOM_GATE_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
AXIOM_GATE_SOURCE_ERROR = "SOURCE_ERROR"
AXIOM_GATE_METRICS_INCOMPLETE = "METRICS_INCOMPLETE"
AXIOM_GATE_THROTTLED = "THROTTLED"

AXIOM_GATE_STATUSES = (
    AXIOM_GATE_PASSED, AXIOM_GATE_FAILED, AXIOM_GATE_SOURCE_UNAVAILABLE, AXIOM_GATE_SOURCE_ERROR,
    AXIOM_GATE_METRICS_INCOMPLETE, AXIOM_GATE_THROTTLED,
)


# --------------------------------------------------------------------------- observe-only telemetry
# Stage change (2026-06-22): Axiom is an OBSERVE / ENRICHMENT / MEASUREMENT layer by DEFAULT. The gate
# still DECODES strictly (so a PASS still means a real, recent, successful, mint-associated active-router
# swap with fee metrics) and REPORTS the decoded fee — so the operator can compare the decoded Axiom fee
# against the Axiom UI number by hand — but the verdict does NOT block a candidate before reserve/send.
# The opt-in ``--require-axiom-pass`` restores the hard gate. The helpers below are pure + redaction-safe.

AXIOM_FINAL_ELIGIBILITY_PHX2_BASELINE = "PHX2_BASELINE_ELIGIBILITY"   # observe-only: PHX2 eligibility decides
AXIOM_FINAL_ELIGIBILITY_HARD_GATE = "AXIOM_PASS_REQUIRED"             # opt-in hard gate: Axiom PASS required
AXIOM_MANUAL_UI_COMPARISON_PENDING = "PENDING"                        # operator fills the UI number by hand

# --------------------------------------------------------------------------- fee-paid telemetry (2026-06-23)
# OBSERVE-ONLY closed-set "fee paid" status, derived PURELY from the already-decoded gate evidence (no new
# network, no inference). It reshapes the per-tx decode into the operator-facing fee-paid vocabulary +
# the compact Discord "Axiom Tx Fees Observed" line. It NEVER fabricates a fee: an unproven fee is reported
# UNAVAILABLE, a failed tx is reported without totals, and "no routed tx" is reported when none was seen.
AXIOM_FEE_PAID_OBSERVED = "FEE_PAID_OBSERVED"                # routed swap + success + a valid total fee
AXIOM_FEE_PAID_METRICS_UNAVAILABLE = "FEE_METRICS_UNAVAILABLE"   # routed swap, but fee metrics missing
AXIOM_FEE_PAID_TX_FAILED = "AXIOM_TX_FAILED"                 # routed swap but the tx failed -> no totals
AXIOM_FEE_PAID_NO_ROUTED_TX = "NO_AXIOM_ROUTED_TX"          # no active Axiom-routed tx observed
AXIOM_FEE_PAID_SOURCE_UNAVAILABLE = "FEE_SOURCE_UNAVAILABLE"   # source unavailable / error / throttled

AXIOM_FEE_PAID_STATUSES = (
    AXIOM_FEE_PAID_OBSERVED, AXIOM_FEE_PAID_METRICS_UNAVAILABLE, AXIOM_FEE_PAID_TX_FAILED,
    AXIOM_FEE_PAID_NO_ROUTED_TX, AXIOM_FEE_PAID_SOURCE_UNAVAILABLE,
)

_LAMPORTS_PER_SOL = Decimal(1_000_000_000)


def lamports_to_sol_str(lamports: Optional[int]) -> Optional[str]:
    """Exact lamports -> SOL as a fixed 9-decimal string (no float error). ``None`` passes through so an
    unavailable fee stays unavailable (never fabricated as 0)."""
    if lamports is None:
        return None
    try:
        return f"{(Decimal(int(lamports)) / _LAMPORTS_PER_SOL):.9f}"
    except Exception:
        return None


def _decode_confidence(m: Dict[str, Any]) -> str:
    """Coarse confidence in the decoded Axiom evidence (telemetry only; never an eligibility input)."""
    if not m or not bool(m.get("axiom_routed_swap_detected")):
        return "NONE"
    has_fee = m.get("total_fee_lamports") is not None and m.get("priority_fee_lamports") is not None
    assoc = m.get("candidate_mint_association_passed") is True
    if has_fee and assoc and m.get("tx_success") is True:
        return "HIGH"
    if has_fee or assoc:
        return "PARTIAL"
    return "LOW"


# --------------------------------------------------------------------------- signals / errors


class AxiomThrottleSignal(Exception):
    """Raised by a real source on upstream rate-limiting (HTTP 429). Gate -> THROTTLED."""


class AxiomFeeSourceError(Exception):
    """Raised by a real source on a hard (non-throttle) RPC/decode failure. Gate -> SOURCE_ERROR."""


# --------------------------------------------------------------------------- data shapes


@dataclass(frozen=True)
class AxiomFeeMetrics:
    """Decoded evidence for one mint (never fabricated). ``axiom_routed_swap_detected`` is True only
    when a TOP-LEVEL instruction called one of the two ACTIVE Axiom routers; fee lamports come from
    the transaction meta (total = meta.fee; base = 5000*num_signatures; priority = total - base)."""

    token_mint: str
    axiom_routed_swap_detected: bool = False
    router_program_id: Optional[str] = None
    router_program_label: Optional[str] = None
    tx_signature: Optional[str] = None
    tx_slot: Optional[int] = None
    tx_success: Optional[bool] = None
    total_fee_lamports: Optional[int] = None
    priority_fee_lamports: Optional[int] = None
    base_fee_lamports: Optional[int] = None
    inner_program_evidence: Optional[Dict[str, bool]] = None
    deprecated_router_seen: bool = False
    # Recency (Blocker 4): a PASS requires a present, sane, non-future, non-ancient blockTime.
    tx_block_time: Optional[int] = None
    tx_age_seconds: Optional[int] = None
    recency_passed: Optional[bool] = None
    recency_reason: Optional[str] = None
    max_tx_age_seconds: Optional[int] = None
    # Candidate-mint association (Codex Blocker 1): a PASS requires the candidate mint to be positively
    # tied to the active-router swap evidence (token balances / parsed token mint / router or inner
    # account keys / PumpFun-Token2022 swap accounts). None => not evaluated (decode-only).
    candidate_mint: Optional[str] = None
    candidate_mint_association_passed: Optional[bool] = None
    candidate_mint_association_sources: Optional[tuple] = None
    router_instruction_index: Optional[int] = None
    matched_token_balance_mints: Optional[tuple] = None
    matched_router_accounts: Optional[tuple] = None
    matched_router_inner_accounts: Optional[tuple] = None
    matched_trusted_programs: Optional[tuple] = None
    ignored_untrusted_mint_mentions: Optional[tuple] = None
    # OBSERVE-ONLY compute telemetry (2026-06-23): read directly from tx meta / a ComputeBudget
    # SetComputeUnitPrice instruction by the source decoder; None when absent (never fabricated). NOT a
    # gate input — enrichment only.
    compute_units_consumed: Optional[int] = None
    compute_unit_price_micro_lamports: Optional[int] = None
    # Per-mint verdict cache (Blocker 8).
    cache_hit: bool = False
    observed_at_utc: Optional[str] = None
    source: str = "UNKNOWN"
    extra: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class AxiomFeeGateConfig:
    """Operator-tunable, conservative-by-default (Paul's blueprint). A platform-fee transfer is NOT
    required (the decoder cannot yet identify one reliably).

    Codex Blocker 2 (2026-06-21): the four strict invariants below default True and the production
    runner REFUSES any injected config that flips one to False (see ``is_strict_axiom_config`` and
    ``run_production_live_watch``). Only ``max_total_fee_lamports`` is a (stricter-only) operator knob."""

    require_success: bool = True            # only a successful tx is positive evidence
    require_fee_metrics: bool = True        # total + priority fee lamports must be present
    require_recent_tx: bool = True          # blockTime present, sane, non-future, non-ancient
    require_candidate_mint_association: bool = True  # candidate mint must be in the active-router swap evidence
    max_total_fee_lamports: Optional[int] = None   # optional ceiling; None => not enforced


# The four invariants that production live MUST enforce (Codex Blocker 2). A config that disables any
# of them is "lax" and the runner refuses it before any source/discovery/ledger/transport work.
def is_strict_axiom_config(config: "AxiomFeeGateConfig") -> bool:
    return bool(
        getattr(config, "require_success", False) is True
        and getattr(config, "require_fee_metrics", False) is True
        and getattr(config, "require_recent_tx", False) is True
        and getattr(config, "require_candidate_mint_association", False) is True
    )


@dataclass(frozen=True)
class AxiomFeeGateResult:
    token_mint: str
    status: str
    passed: bool
    reason: str
    observed_metrics: Dict[str, Any]
    timestamp: str
    source: str

    def to_artifact(self) -> Dict[str, Any]:
        m = self.observed_metrics or {}
        return {
            "kind": "PRODUCTION_LIVE_AXIOM_FEE_GATE",
            "token_mint": self.token_mint,
            "axiom_fee_gate_status": self.status,
            "axiom_fee_gate_passed": bool(self.passed),
            "reason": self.reason,
            "axiom_routed_swap_detected": bool(m.get("axiom_routed_swap_detected", False)),
            "router_program_id": m.get("router_program_id"),
            "router_program_label": m.get("router_program_label"),
            "tx_signature": m.get("tx_signature"),
            "tx_slot": m.get("tx_slot"),
            "tx_success": m.get("tx_success"),
            "total_fee_lamports": m.get("total_fee_lamports"),
            "priority_fee_lamports": m.get("priority_fee_lamports"),
            "base_fee_lamports": m.get("base_fee_lamports"),
            "inner_program_evidence": m.get("inner_program_evidence"),
            "deprecated_router_seen": bool(m.get("deprecated_router_seen", False)),
            "tx_block_time": m.get("tx_block_time"),
            "tx_age_seconds": m.get("tx_age_seconds"),
            "max_tx_age_seconds": m.get("max_tx_age_seconds"),
            "recency_passed": m.get("recency_passed"),
            "candidate_mint": m.get("candidate_mint"),
            "candidate_mint_association_passed": m.get("candidate_mint_association_passed"),
            "candidate_mint_association_sources": m.get("candidate_mint_association_sources") or [],
            "router_instruction_index": m.get("router_instruction_index"),
            "matched_token_balance_mints": m.get("matched_token_balance_mints") or [],
            "matched_router_accounts": m.get("matched_router_accounts") or [],
            "matched_router_inner_accounts": m.get("matched_router_inner_accounts") or [],
            "matched_trusted_programs": m.get("matched_trusted_programs") or [],
            "ignored_untrusted_mint_mentions": m.get("ignored_untrusted_mint_mentions") or [],
            "compute_units_consumed": m.get("compute_units_consumed"),
            "compute_unit_price_micro_lamports": m.get("compute_unit_price_micro_lamports"),
            "cache_hit": bool(m.get("cache_hit", False)),
            # SOL conversions (exact lamports/1e9 as fixed-decimal strings; None stays None) + decode
            # confidence + the manual UI-comparison hook, so the operator can validate the decoded Axiom
            # fee against the Axiom UI number by hand.
            "total_fee_sol": lamports_to_sol_str(m.get("total_fee_lamports")),
            "priority_fee_sol": lamports_to_sol_str(m.get("priority_fee_lamports")),
            "base_fee_sol": lamports_to_sol_str(m.get("base_fee_lamports")),
            "fee_source": self.source,
            "decode_confidence": _decode_confidence(m),
            "manual_ui_comparison_status": AXIOM_MANUAL_UI_COMPARISON_PENDING,
            "manual_ui_fee_sol": None,
            "observed_fee_metrics": m,
            "timestamp": self.timestamp,
            "source": self.source,
        }


@runtime_checkable
class AxiomFeeSource(Protocol):
    source_name: str

    def fetch_fee_metrics(self, token_mint: str) -> Optional[AxiomFeeMetrics]:
        ...


class NullAxiomFeeSource:
    """Fallback when no RPC source is wired. Returns None (no data) — never fabricates. Gate fails
    closed (SOURCE_UNAVAILABLE) so the runner sends nothing."""

    source_name = "NULL_NO_AXIOM_SOURCE_CONFIGURED"

    def fetch_fee_metrics(self, token_mint: str) -> Optional[AxiomFeeMetrics]:  # noqa: D401
        return None


# --------------------------------------------------------------------------- helpers


def metrics_to_dict(metrics: Optional[AxiomFeeMetrics]) -> Dict[str, Any]:
    if metrics is None:
        return {}
    return {
        "token_mint": metrics.token_mint,
        "axiom_routed_swap_detected": bool(metrics.axiom_routed_swap_detected),
        "router_program_id": metrics.router_program_id,
        "router_program_label": metrics.router_program_label,
        "tx_signature": metrics.tx_signature,
        "tx_slot": metrics.tx_slot,
        "tx_success": metrics.tx_success,
        "total_fee_lamports": metrics.total_fee_lamports,
        "priority_fee_lamports": metrics.priority_fee_lamports,
        "base_fee_lamports": metrics.base_fee_lamports,
        "inner_program_evidence": (dict(metrics.inner_program_evidence)
                                   if isinstance(metrics.inner_program_evidence, dict) else None),
        "deprecated_router_seen": bool(metrics.deprecated_router_seen),
        "tx_block_time": metrics.tx_block_time,
        "tx_age_seconds": metrics.tx_age_seconds,
        "recency_passed": metrics.recency_passed,
        "recency_reason": metrics.recency_reason,
        "max_tx_age_seconds": metrics.max_tx_age_seconds,
        "candidate_mint": metrics.candidate_mint,
        "candidate_mint_association_passed": metrics.candidate_mint_association_passed,
        "candidate_mint_association_sources": (list(metrics.candidate_mint_association_sources)
                                               if metrics.candidate_mint_association_sources else []),
        "router_instruction_index": metrics.router_instruction_index,
        "matched_token_balance_mints": (list(metrics.matched_token_balance_mints)
                                        if metrics.matched_token_balance_mints else []),
        "matched_router_accounts": (list(metrics.matched_router_accounts)
                                    if metrics.matched_router_accounts else []),
        "matched_router_inner_accounts": (list(metrics.matched_router_inner_accounts)
                                          if metrics.matched_router_inner_accounts else []),
        "matched_trusted_programs": (list(metrics.matched_trusted_programs)
                                     if metrics.matched_trusted_programs else []),
        "ignored_untrusted_mint_mentions": (list(metrics.ignored_untrusted_mint_mentions)
                                            if metrics.ignored_untrusted_mint_mentions else []),
        "compute_units_consumed": metrics.compute_units_consumed,
        "compute_unit_price_micro_lamports": metrics.compute_unit_price_micro_lamports,
        "cache_hit": bool(metrics.cache_hit),
        "observed_at_utc": metrics.observed_at_utc,
        "source": metrics.source,
        "extra": dict(metrics.extra) if isinstance(metrics.extra, dict) else None,
    }


def _source_name(source: Any) -> str:
    if source is None:
        return "NONE"
    return str(getattr(source, "source_name", type(source).__name__))


def _result(token_mint, status, passed, reason, observed, ts, source) -> AxiomFeeGateResult:
    return AxiomFeeGateResult(token_mint=token_mint, status=status, passed=bool(passed),
                              reason=reason, observed_metrics=observed, timestamp=ts, source=source)


# --------------------------------------------------------------------------- the gate


def evaluate_axiom_fee_gate(
    token_mint: str,
    *,
    source: Optional[AxiomFeeSource],
    config: AxiomFeeGateConfig,
    now_iso_fn,
) -> AxiomFeeGateResult:
    """PURE w.r.t. ledger/transport. Fails closed on any uncertainty so an Axiom-unproven candidate
    never advances to reserve/send."""
    ts = now_iso_fn()
    src_name = _source_name(source)

    if source is None:
        return _result(token_mint, AXIOM_GATE_SOURCE_UNAVAILABLE, False,
                       "NO_AXIOM_FEE_SOURCE_CONFIGURED", {}, ts, "NONE")
    try:
        m = source.fetch_fee_metrics(token_mint)
    except AxiomThrottleSignal:
        return _result(token_mint, AXIOM_GATE_THROTTLED, False, "AXIOM_SOURCE_THROTTLED", {}, ts, src_name)
    except Exception as exc:  # AxiomFeeSourceError / unexpected -> fail closed
        return _result(token_mint, AXIOM_GATE_SOURCE_ERROR, False,
                       "AXIOM_SOURCE_ERROR:" + type(exc).__name__, {}, ts, src_name)

    if m is None:
        return _result(token_mint, AXIOM_GATE_SOURCE_UNAVAILABLE, False,
                       "AXIOM_NO_DECODABLE_TX", {}, ts, src_name)

    observed = metrics_to_dict(m)
    out_source = m.source or src_name

    if not bool(m.axiom_routed_swap_detected):
        reason = "AXIOM_DEPRECATED_ROUTER_ONLY" if m.deprecated_router_seen else "NO_ACTIVE_AXIOM_ROUTER_CALL"
        return _result(token_mint, AXIOM_GATE_FAILED, False, reason, observed, ts, out_source)

    # Defensive: a detected router must be an ACTIVE one (never a deprecated id as pass evidence).
    if not is_active_axiom_router(m.router_program_id):
        return _result(token_mint, AXIOM_GATE_FAILED, False, "ROUTER_NOT_ACTIVE", observed, ts, out_source)

    if config.require_success and m.tx_success is not True:
        return _result(token_mint, AXIOM_GATE_FAILED, False, "AXIOM_TX_FAILED", observed, ts, out_source)

    if config.require_fee_metrics and (m.total_fee_lamports is None or m.priority_fee_lamports is None):
        return _result(token_mint, AXIOM_GATE_METRICS_INCOMPLETE, False,
                       "AXIOM_FEE_METRICS_UNAVAILABLE", observed, ts, out_source)

    # Recency (Blocker 4): the swap must be recent (blockTime present, sane, non-future, non-ancient).
    if config.require_recent_tx and m.recency_passed is not True:
        return _result(token_mint, AXIOM_GATE_FAILED, False,
                       m.recency_reason or "AXIOM_TX_NOT_RECENT", observed, ts, out_source)

    # Candidate-mint association (Codex Blocker 1): the candidate mint must be positively tied to the
    # active-router swap evidence. An active router with NO candidate-mint association FAILS CLOSED —
    # router-program-id presence alone is NOT proof that this mint was the one swapped.
    if config.require_candidate_mint_association and m.candidate_mint_association_passed is not True:
        return _result(token_mint, AXIOM_GATE_FAILED, False,
                       "AXIOM_CANDIDATE_MINT_NOT_ASSOCIATED", observed, ts, out_source)

    if (config.max_total_fee_lamports is not None and m.total_fee_lamports is not None
            and m.total_fee_lamports > config.max_total_fee_lamports):
        return _result(token_mint, AXIOM_GATE_FAILED, False, "AXIOM_TOTAL_FEE_ABOVE_MAX", observed, ts, out_source)

    return _result(token_mint, AXIOM_GATE_PASSED, True, "AXIOM_ROUTED_SWAP_CONFIRMED", observed, ts, out_source)


# --------------------------------------------------------------------------- observe-only builders


def axiom_eligibility_source(require_axiom_pass: bool) -> str:
    """Where the FINAL send eligibility comes from: PHX2 baseline eligibility in observe-only mode (the
    default — Axiom does not decide), or the Axiom hard gate when ``--require-axiom-pass`` is set."""
    return AXIOM_FINAL_ELIGIBILITY_HARD_GATE if require_axiom_pass else AXIOM_FINAL_ELIGIBILITY_PHX2_BASELINE


def build_axiom_observe_fields(result: "AxiomFeeGateResult", *, require_axiom_pass: bool,
                               candidate_blocked: Optional[bool] = None) -> Dict[str, Any]:
    """Mode-dependent telemetry layered on top of ``result.to_artifact()``. In observe-only mode (the
    DEFAULT) Axiom never blocks: ``axiom_observe_only=True``, ``axiom_used_for_blocking=False``,
    ``axiom_blocked_candidate=False``. In opt-in hard-gate mode a non-PASS candidate IS blocked."""
    passed = bool(getattr(result, "passed", False))
    if candidate_blocked is None:
        candidate_blocked = bool(require_axiom_pass and not passed)
    return {
        "axiom_observe_only": (not require_axiom_pass),
        "axiom_used_for_blocking": bool(require_axiom_pass),
        "axiom_blocked_candidate": bool(candidate_blocked),
        "final_send_eligibility_source": axiom_eligibility_source(require_axiom_pass),
        "manual_ui_comparison_status": AXIOM_MANUAL_UI_COMPARISON_PENDING,
    }


def build_axiom_observe_artifact(result: "AxiomFeeGateResult", *, require_axiom_pass: bool,
                                 candidate_blocked: Optional[bool] = None) -> Dict[str, Any]:
    """``result.to_artifact()`` enriched with the observe-only/mode fields. This is the per-evaluation
    ``axiom/<mint8>.jsonl`` record written for EVERY candidate (pass and fail)."""
    art = result.to_artifact()
    art.update(build_axiom_observe_fields(result, require_axiom_pass=require_axiom_pass,
                                          candidate_blocked=candidate_blocked))
    return art


_AXIOM_STATUS_DISPLAY = {
    AXIOM_GATE_PASSED: "decoded",
    AXIOM_GATE_FAILED: "no active Axiom routed tx found",
    AXIOM_GATE_METRICS_INCOMPLETE: "metrics unavailable",
    AXIOM_GATE_SOURCE_UNAVAILABLE: "unavailable",
    AXIOM_GATE_SOURCE_ERROR: "error",
    AXIOM_GATE_THROTTLED: "throttled",
}


def _routed_word(art: Dict[str, Any]) -> str:
    if bool(art.get("axiom_routed_swap_detected")):
        return "yes"
    if art.get("axiom_fee_gate_status") in (AXIOM_GATE_SOURCE_UNAVAILABLE, AXIOM_GATE_SOURCE_ERROR,
                                            AXIOM_GATE_THROTTLED):
        return "unknown"
    return "no"


def _sig_short(sig: Optional[str]) -> Optional[str]:
    if not sig:
        return None
    s = str(sig)
    return s if len(s) <= 14 else (s[:8] + ".." + s[-4:])


def _fee_display(art: Dict[str, Any]) -> str:
    t, p, b = art.get("total_fee_sol"), art.get("priority_fee_sol"), art.get("base_fee_sol")
    if t is None and p is None and b is None:
        return "unavailable"

    def _trim(x: Optional[str]) -> str:
        if x is None:
            return "unknown"
        s = str(x)
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s or "0"
    return f"{_trim(t)} SOL total, {_trim(p)} priority, {_trim(b)} base"


def build_axiom_discord_section(art: Dict[str, Any], *, require_axiom_pass: bool) -> Dict[str, Any]:
    """Compact Axiom section for the private operator Discord payload (structured + rendered ``text``).
    Pure + redaction-safe (no URL / API key / secret). ``art`` is a ``to_artifact()``-shaped dict."""
    mode = "hard-gate" if require_axiom_pass else "observe-only"
    routed = _routed_word(art)
    fee = _fee_display(art)
    sig = _sig_short(art.get("tx_signature"))
    status_word = _AXIOM_STATUS_DISPLAY.get(art.get("axiom_fee_gate_status"), "unavailable")
    lines = ["Axiom:", f"- mode: {mode}", f"- routed: {routed}", f"- fee: {fee}",
             f"- tx: {sig or 'n/a'}", f"- status: {status_word}", "- UI compare: pending manual check"]
    return {"mode": mode, "routed": routed, "fee": fee, "tx": sig, "status": status_word,
            "ui_compare": "pending manual check", "text": "\n".join(lines)}


def _trim_sol_display(value: Optional[str]) -> Optional[str]:
    """Trim trailing zeros from a fixed-decimal SOL string for compact display ("0.000205000" ->
    "0.000205"); None stays None. Display-only — the structured fields keep full 9-decimal precision."""
    if value is None:
        return None
    s = str(value)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _safe_short_reason(reason: Any) -> str:
    """A short, redaction-safe reason token for the Discord 'unavailable (...)' display. The gate reasons
    are already closed-set safe tokens; this bounds length + keeps only safe chars so a malformed reason
    can never inject a URL / secret needle into the rendered line."""
    if not isinstance(reason, str) or reason.strip() == "":
        return "UNAVAILABLE"
    cleaned = "".join(ch for ch in reason.strip() if ch.isalnum() or ch in "_:.-")
    return cleaned[:48] or "UNAVAILABLE"


def _is_safe_sig(value: Any) -> bool:
    """A tx signature is safe-to-echo when it is a bounded base58-ish string with no whitespace / url
    needle. Self-contained (the gate stays dependency-light); the artifact redaction scan is the backstop."""
    if not isinstance(value, str) or not value or len(value) > 120:
        return False
    return not any(b in value for b in ("://", " ", "\n", "\r", "\t"))


def build_axiom_fee_paid(art: Dict[str, Any]) -> Dict[str, Any]:
    """Reshape a ``to_artifact()``-shaped Axiom evidence dict into the OBSERVE-ONLY fee-paid telemetry
    record (the task field vocabulary). PURE + redaction-safe; derives ONLY from already-decoded evidence
    and NEVER fabricates a fee.

    Status (closed set): a routed swap with success + a valid total fee is ``FEE_PAID_OBSERVED``; a
    routed swap with no fee metrics is ``FEE_METRICS_UNAVAILABLE``; a routed-but-FAILED tx is
    ``AXIOM_TX_FAILED`` (totals deliberately withheld — never fabricated); no active routed tx is
    ``NO_AXIOM_ROUTED_TX``; a source error / throttle / no-source is ``FEE_SOURCE_UNAVAILABLE``.

    ``axiom_routed_tx_count`` / ``axiom_fee_total_*`` are computed over the Axiom-routed evidence the
    source decoded for this candidate. The production source decodes ONE representative routed swap per
    mint, so the count is 0 or 1 and the aggregate equals that single tx's total fee."""
    art = art or {}
    gate_status = art.get("axiom_fee_gate_status")
    reason = art.get("reason")
    routed = bool(art.get("axiom_routed_swap_detected"))
    success = art.get("tx_success")
    total_lamports = art.get("total_fee_lamports")

    if gate_status in (AXIOM_GATE_SOURCE_ERROR, AXIOM_GATE_THROTTLED):
        status = AXIOM_FEE_PAID_SOURCE_UNAVAILABLE
    elif gate_status == AXIOM_GATE_SOURCE_UNAVAILABLE:
        # source worked but found no decodable tx -> "no routed tx"; otherwise the source is unavailable.
        status = (AXIOM_FEE_PAID_NO_ROUTED_TX if reason == "AXIOM_NO_DECODABLE_TX"
                  else AXIOM_FEE_PAID_SOURCE_UNAVAILABLE)
    elif not routed:
        status = AXIOM_FEE_PAID_NO_ROUTED_TX
    elif success is not True:
        status = AXIOM_FEE_PAID_TX_FAILED
    elif total_lamports is None:
        status = AXIOM_FEE_PAID_METRICS_UNAVAILABLE
    else:
        status = AXIOM_FEE_PAID_OBSERVED

    fee_proven = (status == AXIOM_FEE_PAID_OBSERVED)
    routed_tx_count = 1 if status in (AXIOM_FEE_PAID_OBSERVED, AXIOM_FEE_PAID_METRICS_UNAVAILABLE,
                                      AXIOM_FEE_PAID_TX_FAILED) else 0

    # Only an OBSERVED (recent, successful, fee-valid) swap surfaces fee totals. A failed / metrics-
    # missing / no-tx / source-down state reports the fee UNAVAILABLE rather than fabricate a number
    # (a failed tx's decoded total is deliberately withheld here per "do not fake fee totals").
    total_fee_lamports = total_lamports if fee_proven else None
    base_fee_lamports = art.get("base_fee_lamports") if fee_proven else None
    priority_fee_lamports = art.get("priority_fee_lamports") if fee_proven else None
    cu = art.get("compute_units_consumed") if fee_proven else None
    cu_price = art.get("compute_unit_price_micro_lamports") if fee_proven else None

    def _int_or_none(v):
        return v if (isinstance(v, int) and not isinstance(v, bool)) else None

    sig = art.get("tx_signature")
    return {
        "kind": "PRODUCTION_LIVE_AXIOM_FEE_PAID",
        "axiom_observe_only": True,
        "axiom_used_for_blocking": False,
        "axiom_blocked_candidate": False,
        "axiom_fee_status": status,
        "axiom_fee_reason": (reason if isinstance(reason, str) and reason else status),
        "axiom_tx_signature": (sig if _is_safe_sig(sig) else None),
        "axiom_tx_success": (success if isinstance(success, bool) else None),
        "axiom_total_fee_lamports": total_fee_lamports,
        "axiom_total_fee_sol": lamports_to_sol_str(total_fee_lamports),
        "axiom_routed_tx_count": routed_tx_count,
        "axiom_fee_total_lamports": total_fee_lamports,
        "axiom_fee_total_sol": lamports_to_sol_str(total_fee_lamports),
        # optional fields — present ONLY when safely derivable; otherwise None (unavailable).
        "axiom_base_fee_lamports": base_fee_lamports,
        "axiom_base_fee_sol": lamports_to_sol_str(base_fee_lamports),
        "axiom_priority_fee_lamports": priority_fee_lamports,
        "axiom_priority_fee_sol": lamports_to_sol_str(priority_fee_lamports),
        "axiom_compute_units_consumed": _int_or_none(cu),
        "axiom_compute_unit_price_micro_lamports": _int_or_none(cu_price),
        # Display-scope clarity (2026-06-24 DBX reconciliation): this metric is the OBSERVED Solana
        # network transaction fee(s) of decoded Axiom-routed swaps — NOT the Axiom UI lifetime/platform
        # fee (proven NOT_RECONCILED: ~0.0108 SOL observed vs ~9.943 SOL UI). Additive note fields only.
        "axiom_fee_metric_label": "AXIOM_TX_FEES_OBSERVED",
        "axiom_fee_metric_scope": "OBSERVED_ROUTED_TX_NETWORK_FEES_NOT_LIFETIME",
    }


def build_axiom_fees_discord_line(fee_paid: Dict[str, Any]) -> str:
    """The compact, redaction-safe 'Axiom Tx Fees Observed' line(s) for the PRIVATE operator Discord ping body, in
    the required display format. PURE; never includes a URL / API key / secret / raw JSON blob. The
    optional Priority / Compute lines appear ONLY when the fee was OBSERVED and those values are present
    (so the line stays short and never contradicts an 'unavailable' main line)."""
    fp = fee_paid or {}
    status = fp.get("axiom_fee_status")
    if status == AXIOM_FEE_PAID_OBSERVED and fp.get("axiom_total_fee_sol") is not None:
        total = _trim_sol_display(fp.get("axiom_total_fee_sol"))
        lines = [f"Axiom Tx Fees Observed: {total} SOL total / {fp.get('axiom_routed_tx_count')} routed txs"]
        prio = _trim_sol_display(fp.get("axiom_priority_fee_sol"))
        if prio is not None:
            lines.append(f"Priority Fee: {prio} SOL")
        cu = fp.get("axiom_compute_units_consumed")
        if isinstance(cu, int) and not isinstance(cu, bool):
            price = fp.get("axiom_compute_unit_price_micro_lamports")
            price_disp = price if (isinstance(price, int) and not isinstance(price, bool)) else "unknown"
            lines.append(f"Compute: {cu} CU @ {price_disp} micro-lamports/CU")
        return "\n".join(lines)
    if status == AXIOM_FEE_PAID_NO_ROUTED_TX:
        return "Axiom Tx Fees Observed: no routed tx observed"
    return f"Axiom Tx Fees Observed: unavailable ({_safe_short_reason(fp.get('axiom_fee_reason'))})"


def compose_private_ping_with_axiom(body: str, fee_paid: Dict[str, Any]) -> str:
    """Return a private operator ping body with the OBSERVE-ONLY Axiom Tx Fees Observed line appended.

    This is the OUT-OF-REPO display SEAM. It is exercised offline against a FAKE ping body in the
    selftest; it is NOT wired into the committed live body composer. The live body is built by the
    committed Stage 30.12 renderer and forwarded verbatim by the committed Stage 30.11.16 guard under a
    locked ``{"content": body}`` allowlist, so injecting this line into a REAL send would require either
    a committed-repo edit or an out-of-repo transport wrapper (see the build report — deferred, not done
    here). Pure; appends only the redaction-safe Axiom Tx Fees Observed line, changes NO eligibility, opens NO
    transport."""
    base = body if isinstance(body, str) else ""
    line = build_axiom_fees_discord_line(fee_paid)
    return (base.rstrip("\n") + "\n" + line) if base.strip() else line


def build_axiom_send_summary(result: Optional["AxiomFeeGateResult"], *, require_axiom_pass: bool
                             ) -> Dict[str, Any]:
    """Compact Axiom telemetry attached to a reserve/send artifact AND ready for the Discord body. A
    reserved/sent candidate was ALLOWED, so ``axiom_blocked_candidate`` is always False here. ``result``
    is ``None`` only when the EXACT reserved candidate (hence its Axiom telemetry) is not known."""
    base = {
        "kind": "PRODUCTION_LIVE_AXIOM_OBSERVE",
        "axiom_observe_only": (not require_axiom_pass),
        "axiom_used_for_blocking": bool(require_axiom_pass),
        "axiom_blocked_candidate": False,
        "final_send_eligibility_source": axiom_eligibility_source(require_axiom_pass),
        "manual_ui_comparison_status": AXIOM_MANUAL_UI_COMPARISON_PENDING,
        "manual_ui_fee_sol": None,
    }
    if result is None:
        art = {"axiom_fee_gate_status": None, "axiom_routed_swap_detected": False, "tx_signature": None,
               "total_fee_sol": None, "priority_fee_sol": None, "base_fee_sol": None}
        base.update({
            "axiom_status": None, "axiom_passed": None,
            "axiom_reason": "AXIOM_TELEMETRY_UNAVAILABLE_FOR_RESERVED_CANDIDATE",
            "axiom_routed_swap_detected": None, "router_program_id": None, "router_program_label": None,
            "tx_signature": None, "tx_slot": None, "tx_success": None,
            "candidate_mint_association_passed": None, "total_fee_lamports": None,
            "priority_fee_lamports": None, "base_fee_lamports": None, "total_fee_sol": None,
            "priority_fee_sol": None, "base_fee_sol": None, "fee_source": None, "cache_hit": None,
            "tx_age_seconds": None, "decode_confidence": "NONE",
        })
        base["axiom_discord_section"] = build_axiom_discord_section(art, require_axiom_pass=require_axiom_pass)
        base["axiom_fee_paid"] = build_axiom_fee_paid({
            "axiom_fee_gate_status": AXIOM_GATE_SOURCE_UNAVAILABLE,
            "reason": "AXIOM_TELEMETRY_UNAVAILABLE_FOR_RESERVED_CANDIDATE",
            "axiom_routed_swap_detected": False})
        base["axiom_fees_line"] = build_axiom_fees_discord_line(base["axiom_fee_paid"])
        return base
    art = result.to_artifact()
    base.update({
        "axiom_status": art.get("axiom_fee_gate_status"),
        "axiom_passed": bool(art.get("axiom_fee_gate_passed")),
        "axiom_reason": art.get("reason"),
        "axiom_routed_swap_detected": bool(art.get("axiom_routed_swap_detected")),
        "router_program_id": art.get("router_program_id"),
        "router_program_label": art.get("router_program_label"),
        "tx_signature": art.get("tx_signature"), "tx_slot": art.get("tx_slot"),
        "tx_success": art.get("tx_success"),
        "candidate_mint_association_passed": art.get("candidate_mint_association_passed"),
        "total_fee_lamports": art.get("total_fee_lamports"),
        "priority_fee_lamports": art.get("priority_fee_lamports"),
        "base_fee_lamports": art.get("base_fee_lamports"),
        "total_fee_sol": art.get("total_fee_sol"), "priority_fee_sol": art.get("priority_fee_sol"),
        "base_fee_sol": art.get("base_fee_sol"), "fee_source": art.get("fee_source") or art.get("source"),
        "cache_hit": art.get("cache_hit"), "tx_age_seconds": art.get("tx_age_seconds"),
        "decode_confidence": art.get("decode_confidence"),
    })
    base["axiom_discord_section"] = build_axiom_discord_section(art, require_axiom_pass=require_axiom_pass)
    base["axiom_fee_paid"] = build_axiom_fee_paid(art)
    base["axiom_fees_line"] = build_axiom_fees_discord_line(base["axiom_fee_paid"])
    return base


def build_axiom_fee_source_from_env() -> Optional[AxiomFeeSource]:
    """Production factory. Builds the REAL Helius-RPC Axiom decode source if an RPC URL is present in
    env; otherwise returns ``NullAxiomFeeSource`` (fail-closed). Lazily imports the source module so
    this gate module stays import-time network-free and dependency-light."""
    try:
        from production_live_axiom_source import build_helius_axiom_fee_source_from_env
        src = build_helius_axiom_fee_source_from_env()
        return src if src is not None else NullAxiomFeeSource()
    except Exception:
        return NullAxiomFeeSource()


__all__ = (
    "AXIOM_ROUTER_TRADING_PROGRAM_1", "AXIOM_ROUTER_TRADING_PROGRAM_1_BLUEPRINT",
    "AXIOM_ROUTER_AXIOM_TRADE", "AXIOM_ACTIVE_ROUTER_PROGRAMS",
    "AXIOM_DEPRECATED_ROUTER_CANONICAL", "AXIOM_DEPRECATED_ROUTER_PROGRAMS", "router_label",
    "is_active_axiom_router", "is_deprecated_axiom_router",
    "AXIOM_GATE_PASSED", "AXIOM_GATE_FAILED", "AXIOM_GATE_SOURCE_UNAVAILABLE",
    "AXIOM_GATE_SOURCE_ERROR", "AXIOM_GATE_METRICS_INCOMPLETE", "AXIOM_GATE_THROTTLED",
    "AXIOM_GATE_STATUSES", "AxiomThrottleSignal", "AxiomFeeSourceError",
    "AxiomFeeMetrics", "AxiomFeeGateConfig", "AxiomFeeGateResult", "AxiomFeeSource",
    "NullAxiomFeeSource", "metrics_to_dict", "evaluate_axiom_fee_gate",
    "is_strict_axiom_config", "build_axiom_fee_source_from_env",
    # observe-only (2026-06-22)
    "AXIOM_FINAL_ELIGIBILITY_PHX2_BASELINE", "AXIOM_FINAL_ELIGIBILITY_HARD_GATE",
    "AXIOM_MANUAL_UI_COMPARISON_PENDING", "lamports_to_sol_str", "axiom_eligibility_source",
    "build_axiom_observe_fields", "build_axiom_observe_artifact", "build_axiom_discord_section",
    "build_axiom_send_summary",
    # fee-paid telemetry + Discord display (2026-06-23; observe-only, additive)
    "AXIOM_FEE_PAID_OBSERVED", "AXIOM_FEE_PAID_METRICS_UNAVAILABLE", "AXIOM_FEE_PAID_TX_FAILED",
    "AXIOM_FEE_PAID_NO_ROUTED_TX", "AXIOM_FEE_PAID_SOURCE_UNAVAILABLE", "AXIOM_FEE_PAID_STATUSES",
    "build_axiom_fee_paid", "build_axiom_fees_discord_line", "compose_private_ping_with_axiom",
)
