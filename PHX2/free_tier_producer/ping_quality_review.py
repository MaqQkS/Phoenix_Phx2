"""Redaction-safe 24-hour ping-quality review projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from PHX2.models.market_data_source import normalize_market_data_source


PING_QUALITY_REVIEW_BASENAME = "phx2_ping_quality_review.jsonl"
PING_QUALITY_REVIEW_SCHEMA = "phx2_ping_quality_review_v1"

# ---------------------------------------------------------------------------
# Migration decode-latency OBSERVABILITY (2026-07-27 remediation, point 6).
#
# These are ACCEPTANCE-REVIEW criteria, not eligibility rules: no gate,
# dispatch decision, or admission path reads them.  They exist so the next
# fresh acceptance run can measure, for every live migration, how far behind
# the chain the decode/admission pipeline ran (KEN was decoded ~11 minutes
# after pair creation, after its ATH had already passed) without inventing an
# unapproved production threshold.
# ---------------------------------------------------------------------------

MIGRATION_LATENCY_SCHEMA = "phx2_migration_latency_observability_v1"
#: Review flag: a live migration decoded this long after its chain/provider
#: event time deserves a line in the acceptance report.
MIGRATION_DECODE_LATENCY_REVIEW_SECONDS = 90.0
#: Failure-review flag: the acceptance report must explain every one of these.
MIGRATION_DECODE_LATENCY_EXTREME_SECONDS = 600.0

LATENCY_REVIEW_OK = "OK"
LATENCY_REVIEW_REVIEW = "REVIEW"
LATENCY_REVIEW_EXTREME = "EXTREME"
LATENCY_REVIEW_UNAVAILABLE = "UNAVAILABLE"


def _parse_utc_epoch(value: object) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def _seconds_between(start: object, end: object) -> Optional[float]:
    begin = _parse_utc_epoch(start)
    finish = _parse_utc_epoch(end)
    if begin is None or finish is None:
        return None
    return round(finish - begin, 3)


def classify_decode_latency(seconds: object) -> str:
    """Closed-set review classification for a migration-to-decode latency.

    Pure / total.  ``UNAVAILABLE`` when the latency could not be computed
    (missing chain time or decode time -- e.g. a restart-backfill candidate,
    which has no live decode at all).
    """
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return LATENCY_REVIEW_UNAVAILABLE
    if seconds >= MIGRATION_DECODE_LATENCY_EXTREME_SECONDS:
        return LATENCY_REVIEW_EXTREME
    if seconds >= MIGRATION_DECODE_LATENCY_REVIEW_SECONDS:
        return LATENCY_REVIEW_REVIEW
    return LATENCY_REVIEW_OK


def build_migration_latency_observability(
    *,
    candidate: Mapping[str, Any],
    activation: Mapping[str, Any],
    central_ath: Mapping[str, Any],
) -> Dict[str, Any]:
    """Pure per-candidate latency block from fields the pipeline ALREADY
    persists (no new logging system): the chain/provider migration time and
    slot, the live decode receipt time, the admission (seed) time, the
    activation time, and the first authenticated market observation.  Every
    field is optional and None-safe; a missing input yields None latencies
    and an ``UNAVAILABLE`` review class rather than a fabricated number.
    """
    migration_time = candidate.get("migration_time_utc")
    decode_time = candidate.get("local_observed_at_utc")
    admission_time = (
        candidate.get("seeded_at_utc") or candidate.get("discovery_utc"))
    activation_time = activation.get("activated_at_utc")
    first_market = (
        activation.get("activation_evidence_ingested_at_utc")
        or activation.get("migration_market_cap_observed_at_utc"))
    ath_time = central_ath.get("ath_timestamp")
    migration_to_decode = _seconds_between(migration_time, decode_time)
    admission_epoch = _parse_utc_epoch(admission_time)
    ath_epoch = _parse_utc_epoch(ath_time)
    ath_before_admission: Optional[bool] = None
    if admission_epoch is not None and ath_epoch is not None:
        ath_before_admission = ath_epoch < admission_epoch
    return {
        "latency_schema": MIGRATION_LATENCY_SCHEMA,
        "migration_slot": candidate.get("migration_slot"),
        "migration_time_utc": migration_time,
        "migration_time_source": candidate.get("migration_time_source"),
        "migration_time_authoritative": candidate.get(
            "migration_time_authoritative"),
        "decode_observed_at_utc": decode_time,
        "admission_at_utc": admission_time,
        "activated_at_utc": activation_time,
        "first_authenticated_market_observation_utc": first_market,
        "migration_to_decode_seconds": migration_to_decode,
        "decode_to_admission_seconds": _seconds_between(
            decode_time, admission_time),
        "migration_to_admission_seconds": _seconds_between(
            migration_time, admission_time),
        "admission_to_activation_seconds": _seconds_between(
            admission_time, activation_time),
        "ath_timestamp_utc": ath_time,
        "ath_before_admission": ath_before_admission,
        "provenance": candidate.get("discovery_provenance"),
        "decode_latency_review": classify_decode_latency(migration_to_decode),
        "review_threshold_seconds": MIGRATION_DECODE_LATENCY_REVIEW_SECONDS,
        "extreme_threshold_seconds": MIGRATION_DECODE_LATENCY_EXTREME_SECONDS,
        "review_semantics": "OBSERVABILITY_ACCEPTANCE_REVIEW_ONLY",
    }

_FORBIDDEN_KEYS = frozenset({
    "transaction_signature",
    "signature",
    "raw_transaction",
    "raw_response",
    "response_body",
    "outbound_body",
    "message_body",
    "telegram_token",
    "telegram_chat_id",
    "confirm_token",
})


def _safe_mapping(value: object) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if str(key).lower() not in _FORBIDDEN_KEYS
        and isinstance(item, (str, int, float, bool, type(None)))
    }


CANONICAL_VOLUME_MISSING_REQUIREMENT_BACKFILL = (
    "SEALED_LIVE_MIGRATION_PROOF_REQUIRED_FOR_TRUSTED_SWAP_ROUTING")
CANONICAL_VOLUME_MISSING_REQUIREMENT_LIVE = (
    "AUTHENTICATED_AMOUNT_BEARING_SWAPS_ABSENT_IN_WINDOW")


def _canonical_volume_review(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Explain exactly what canonical volume still requires (artifact-only).

    A restart-backfill admission has no sealed live migration proof, so its
    decoded swaps can never authenticate for trusted routing; a live admission
    with zero samples simply observed no authenticated amount-bearing swaps in
    the trailing window.  Never a gate input.
    """

    snapshot = candidate.get("canonical_volume_5m")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    status = snapshot.get("status")
    missing: Any = None
    if status != "VALID":
        if candidate.get(
                "discovery_provenance") == "DEXSCREENER_RESTART_BACKFILL":
            missing = CANONICAL_VOLUME_MISSING_REQUIREMENT_BACKFILL
        else:
            missing = CANONICAL_VOLUME_MISSING_REQUIREMENT_LIVE
    return {
        "status": status,
        "sample_count": snapshot.get("sample_count"),
        "coverage_seconds": snapshot.get("coverage_seconds"),
        "gross_volume_usd": snapshot.get("gross_volume_usd"),
        "net_quote_flow_usd": snapshot.get("net_quote_flow_usd"),
        "missing_requirement": missing,
    }


def _global_fees_review(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Project the observe-only Global Fees snapshot for review (artifact-only).

    Preserves value, provenance, freshness, failure diagnostics, and any
    disclosed provider regression exactly as the canonical tracker reports
    them.  Never a gate input.
    """

    snapshot = candidate.get("global_fees")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    return {
        "status": snapshot.get("global_fees_status"),
        "global_fees_paid_sol": snapshot.get("global_fees_paid_sol"),
        "interval": snapshot.get("global_fees_interval"),
        "source": snapshot.get("global_fees_source"),
        "endpoint_source": snapshot.get("global_fees_endpoint_source"),
        "observed_at_utc": snapshot.get("global_fees_observed_at_utc"),
        "age_seconds": snapshot.get("global_fees_age_seconds"),
        "http_status_class": snapshot.get("global_fees_http_status_class"),
        "failure_reason": snapshot.get("global_fees_failure_reason"),
        "raw_type": snapshot.get("global_fees_raw_type"),
        "request_reused": snapshot.get("global_fees_request_reused"),
        "regression_detected": snapshot.get(
            "global_fees_regression_detected"),
        "regression_prior_value_sol": snapshot.get(
            "global_fees_regression_prior_value_sol"),
        "regression_prior_observed_at_utc": snapshot.get(
            "global_fees_regression_prior_observed_at_utc"),
        "provider_coverage_note": snapshot.get(
            "global_fees_provider_coverage_note"),
    }


def build_ping_quality_record(
    *,
    candidate: Mapping[str, Any],
    recheck: Mapping[str, Any],
    security: object,
    observed_at_utc: str,
) -> Dict[str, Any]:
    """Project required review fields without a transport body or signature."""

    market = _safe_mapping(recheck.get("market_context"))
    activation = _safe_mapping(
        recheck.get("activation") or candidate.get("activation"))
    central_ath = _safe_mapping(
        recheck.get("central_ath")
        or (recheck.get("market_context") or {}).get("central_ath"))
    security_dict = (
        security.to_dict() if hasattr(security, "to_dict")
        else dict(security) if isinstance(security, Mapping) else {})
    reason = recheck.get("reason")
    sent = reason == "SENT_OK_COMMITTED"
    metadata_state = candidate.get("canonical_token_metadata")
    metadata_state = (metadata_state
                      if isinstance(metadata_state, Mapping) else {})
    raw_market = recheck.get("market_context")
    raw_market = raw_market if isinstance(raw_market, Mapping) else {}
    reserve = raw_market.get("pumpswap_reserve")
    reserve = reserve if isinstance(reserve, Mapping) else {}
    return {
        "schema_version": PING_QUALITY_REVIEW_SCHEMA,
        "observed_at_utc": observed_at_utc,
        "candidate_identity": candidate.get("candidate_id"),
        "mint": candidate.get("token_mint"),
        "symbol_or_name": candidate.get("symbol_or_name"),
        "token_name": candidate.get("token_name"),
        "token_metadata": {
            "token_name": metadata_state.get("token_name"),
            "token_symbol": metadata_state.get("token_symbol"),
            "metadata_status": metadata_state.get("metadata_status"),
            "metadata_source": metadata_state.get("metadata_source"),
            "metadata_first_requested_at": metadata_state.get(
                "metadata_first_requested_at"),
            "metadata_resolved_at": metadata_state.get("metadata_resolved_at"),
            "metadata_attempt_count": metadata_state.get(
                "metadata_attempt_count"),
            "metadata_failure_reason": metadata_state.get(
                "metadata_failure_reason"),
        },
        "canonical_volume_review": _canonical_volume_review(candidate),
        "global_fees_review": _global_fees_review(candidate),
        "actual_reserve_review": {
            "reserve_validation_status": reserve.get(
                "reserve_validation_status"),
            "actual_pool_tvl_usd": reserve.get("actual_pool_tvl_usd"),
            "actual_quote_liquidity_usd": reserve.get(
                "actual_quote_liquidity_usd"),
            "quote_price_observed_at_utc": reserve.get(
                "quote_price_observed_at_utc"),
        },
        "initial_provenance": candidate.get("discovery_provenance"),
        "epoch_id": candidate.get("live_epoch_id"),
        "migration_time_utc": candidate.get("migration_time_utc"),
        "migration_slot": candidate.get("migration_slot"),
        "migration_market_cap_usd": activation.get(
            "migration_market_cap_usd"),
        "post_migration_ath_usd": central_ath.get("ath_market_cap"),
        "current_market_cap_usd": market.get("current_market_cap_usd"),
        "current_price_usd": market.get("current_price"),
        "floor_drawdown_pct": (
            recheck.get("compose_drawdown_pct")
            or market.get("drawdown_pct")),
        "tier": recheck.get("compose_tier"),
        "liquidity_usd": market.get("liquidity_usd"),
        "pair_address": candidate.get("pair_address"),
        "pool_dex_identity": candidate.get("pool_dex_identity"),
        "migration_evidence_class": candidate.get(
            "migration_evidence_class"),
        "migration_market_cap_source": candidate.get(
            "migration_market_cap_source"),
        "ath_source": candidate.get("ath_source"),
        "liquidity_source": candidate.get("liquidity_source"),
        "current_data_source": normalize_market_data_source(
            candidate.get("current_data_source")),
        "source_confidence": candidate.get("source_confidence"),
        "dedupe_identity": candidate.get("dedupe_identity"),
        "corroborating_sources": list(
            candidate.get("corroborating_sources") or []),
        "structural_original_verdict": security_dict.get(
            "original_phx1_structural_verdict"),
        "structural_effective_verdict": security_dict.get(
            "effective_phx1_policy_verdict"),
        "shadow_reasons": list(
            security_dict.get("shadow_warning_reason_tokens") or []),
        "safety_reasons": list(
            security_dict.get("non_shadowable_safety_reason_tokens") or []),
        "eligibility_result": reason,
        "composition_result": recheck.get("compose_decision"),
        "dedupe_result": recheck.get("dedupe_reason"),
        "delivery_result": reason,
        "SENT_OK_COMMITTED": sent,
        "latency_observability": build_migration_latency_observability(
            candidate=candidate, activation=activation,
            central_ath=central_ath),
        "operator_label": None,
        "operator_notes": None,
        "later_outcome": None,
    }


def ping_quality_record_is_redaction_safe(record: Mapping[str, Any]) -> bool:
    """Structural no-secret/no-body check used by tests and runtime."""

    if not isinstance(record, Mapping):
        return False
    keys = {str(key).lower() for key in record}
    if keys & _FORBIDDEN_KEYS:
        return False
    for key, value in record.items():
        lowered = str(key).lower()
        if any(needle in lowered for needle in (
                "secret", "token", "chat_id", "signature", "raw_response",
                "body")) and lowered not in (
                    # Benign token-identity keys (never a credential surface);
                    # everything else containing "token" stays banned.
                    "token_name", "token_symbol", "token_mint",
                    "token_metadata", "telegram_result"):
            return False
        if isinstance(value, Mapping) and not ping_quality_record_is_redaction_safe(
                value):
            return False
    return True


__all__ = (
    "PING_QUALITY_REVIEW_BASENAME",
    "PING_QUALITY_REVIEW_SCHEMA",
    "CANONICAL_VOLUME_MISSING_REQUIREMENT_BACKFILL",
    "CANONICAL_VOLUME_MISSING_REQUIREMENT_LIVE",
    "MIGRATION_LATENCY_SCHEMA",
    "MIGRATION_DECODE_LATENCY_REVIEW_SECONDS",
    "MIGRATION_DECODE_LATENCY_EXTREME_SECONDS",
    "LATENCY_REVIEW_OK",
    "LATENCY_REVIEW_REVIEW",
    "LATENCY_REVIEW_EXTREME",
    "LATENCY_REVIEW_UNAVAILABLE",
    "classify_decode_latency",
    "build_migration_latency_observability",
    "build_ping_quality_record",
    "ping_quality_record_is_redaction_safe",
)
