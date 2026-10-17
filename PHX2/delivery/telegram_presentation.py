"""Compact PHX1-style discovery caption; PHX2 evidence stays explicit.

No providers, configuration, eligibility decisions or paper fills are owned here.
The detailed research composer remains available for offline diagnostic views.
"""
from __future__ import annotations

from .telegram_composer import (
    TelegramComposeResult, TelegramMessageTooLong, TelegramPingData,
    TELEGRAM_INTERNAL_MAX_CHARACTERS, _PresentationBoundary, _e,
    rendered_character_count,
)
from PHX2.models.ath_coverage import ath_coverage_is_complete


def compose_discovery_alert(data: TelegramPingData) -> TelegramComposeResult:
    boundary = _PresentationBoundary()
    def metric(name: str, value: object) -> str:
        return _e(boundary.dash(name, value))

    ath_label = "Post-mig ATH" if ath_coverage_is_complete(data.ath_coverage) else "Obs ATH"
    coverage = {
        "COMPLETE_LIVE": "Complete since migration",
        "COMPLETE_HYDRATED": "Complete (restart backfill hydrated)",
        "PARTIAL_SINCE_ADMISSION": "Partial (restart backfill)",
        "UNKNOWN": "Unknown",
    }[data.ath_coverage]
    provenance = {
        "LIVE": "Live migration", "HELIUS_LIVE": "Live migration",
        "MERGED": "Merged discovery evidence",
        "DEXSCREENER_RESTART_BACKFILL": "Restart backfill", "UNKNOWN": "Unknown",
    }[data.discovery_provenance]
    fees = boundary.optional("global_fees", data.global_fees_display)
    risk = boundary.optional("risk", data.risk_warning)
    lines = [
        f"<b>🔥 PHOENIX — {_e(data.token_identity)} [Tier {data.tier}]</b>",
        f"<code>{_e(data.token_mint)}</code>",
        "Discovery alert · no paper fill implied",
        "",
        "<b>📊 State</b>",
        f"• MC: {metric('market_cap', data.market_cap)} | {ath_label}: "
        f"{metric('post_migration_ath', data.post_migration_ath)} | "
        f"Mig: {metric('migration_market_cap', data.migration_market_cap)}",
        f"• Floor: {metric('floor', data.floor)} | Age: {_e(data.age_display)}",
        f"• LP: {metric('liquidity', data.liquidity)} | Vol 5m: {metric('volume', data.volume)}",
        "",
        f"💰 Global Fees: {_e(fees) if fees else 'Pending / unavailable'}",
        f"• Risk: {_e(risk) if risk else 'Unverified'}",
        f"• Source: {provenance}",
        f"• Coverage: {coverage}",
    ]
    if data.manual_review_required:
        reason = boundary.optional("policy", data.policy_reason_display)
        lines.append(f"⚠ Policy: SHADOW BLOCK - {_e(reason or 'structural shadow block')}")
        lines.append("Manual review required · organicity unverified")
    else:
        boundary.not_applicable("policy")
    # Detailed metrics are retained in compose artifacts, not duplicated in the caption.
    for name in ("fee_gate", "fee_breakdown", "structure_read", "ante_last20",
                 "ante_5m", "ante_widths", "priority_fee", "shape_5m",
                 "shape_last20", "base_fee_coverage", "builder_read"):
        boundary.not_applicable(name)
    message = "\n".join(lines)
    count = rendered_character_count(message)
    if count > TELEGRAM_INTERNAL_MAX_CHARACTERS:
        raise TelegramMessageTooLong()
    return TelegramComposeResult(
        text=message, rendered_character_count=count,
        builder_reason_map={s.text: s.reason_codes for s in data.builder_read},
        field_reason_codes=dict(data.field_reason_codes),
        field_presentation=dict(boundary.statuses),
    )
