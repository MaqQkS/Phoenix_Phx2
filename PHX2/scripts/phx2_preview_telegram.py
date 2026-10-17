"""Self-contained synthetic Telegram review. No network or configuration reads."""
from __future__ import annotations

import argparse
import base64
import io
from dataclasses import MISSING, fields, replace
from html import escape
from pathlib import Path
from types import SimpleNamespace

from PHX2.delivery.telegram_composer import TelegramPingData
from PHX2.delivery.telegram_presentation import compose_discovery_alert
from PHX2.delivery.telegram_media import build_coin_banner, load_pillow
from PHX2.paper_trading.notifications import make_notification


def example() -> TelegramPingData:
    values = {f.name: "" for f in fields(TelegramPingData)
              if f.default is MISSING and f.default_factory is MISSING}
    values.update(token_mint="11111111111111111111111111111111",
                  token_identity="Example Token ($DEMO)", token_metadata_source="SYNTHETIC",
                  age_minutes=22, age_display="22m", tier=2,
                  market_cap="$24k", post_migration_ath="$80k", migration_market_cap="$32k",
                  floor="-70%", volume="$4.2k gross | $1.1k net (n=42)", liquidity="$18k",
                  global_fees_display="14.8 SOL", risk_warning="Medium - LP falling")
    return TelegramPingData(**values)


def synthetic_banner():
    """Pass locally generated pixels through the actual production renderer."""
    pillow = load_pillow()
    if pillow is None:
        return None, "PILLOW_UNAVAILABLE"
    Image, _, _ = pillow
    from PIL import ImageDraw
    logo = Image.new("RGBA", (256, 256), (11, 31, 46, 255))
    draw = ImageDraw.Draw(logo)
    draw.ellipse((20, 20, 236, 236), fill=(51, 185, 190, 255))
    draw.polygon([(64, 174), (106, 70), (133, 129), (183, 57), (161, 183)],
                 fill=(255, 210, 95, 255))
    output = io.BytesIO()
    logo.save(output, format="PNG")
    return build_coin_banner(output.getvalue(), pillow=pillow)


def preview_html(banner_bytes=None) -> str:
    base = example()
    samples = [
        ("Logo banner + caption", base, True),
        ("Text fallback: logo missing or unavailable", replace(base, global_fees_display="",
            risk_warning="", liquidity=""), False),
        ("Partial coverage + required review", replace(base,
            discovery_provenance="DEXSCREENER_RESTART_BACKFILL",
            ath_coverage="PARTIAL_SINCE_ADMISSION", phx1_structural_policy_mode="SHADOW",
            original_phx1_structural_verdict="HARD_BLOCK",
            effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
            shadow_warning_reasons=("SYNTHETIC_EXAMPLE",), manual_review_required=True,
            policy_reason_display="Liquidity evidence incomplete"), False),
    ]
    cards = []
    for title, data, banner in samples:
        result = compose_discovery_alert(data)
        art = ""
        if banner:
            art = (f'<img class="banner" alt="Synthetic production-rendered logo banner" '
                   f'src="data:image/png;base64,{base64.b64encode(banner_bytes).decode()}">'
                   if banner_bytes else '<div class="banner"><span>DEMO</span></div>')
        cards.append(f'<section><h2>{escape(title)}</h2><article>{art}'
                     f'<div class="caption">{result.text}</div></article>'
                     f'<p>{result.rendered_character_count} UTF-16 units - no buttons</p></section>')
    position = SimpleNamespace(paper_trade_id="synthetic-001", mint=base.token_mint,
        strategy_name="bala_plan", risk_label_at_entry="RISK_LOW", cost_basis_usd=100.0,
        strategy_state={"initial_recovery_proceeds_usd": 100.0},
        plan=SimpleNamespace(trailing_stop_pct=0.30), latest_price_epoch=1000.0,
        status="STOPPED", reason_closed="TRAILING_STOP_0.30", realized_pnl_usd=43.7454)
    for transition in ("ENTRY", "STAKE_RECOVERED", "FINAL_EXIT"):
        event = make_notification("synthetic-review", position, transition, 1000.0)
        cards.append(f'<section><h2>Paper {escape(transition.lower().replace("_", " "))}</h2>'
                     f'<article><div class="caption">{event["text"]}</div></article>'
                     '<p>Production outbox formatter; synthetic state; no message sent</p></section>')
    image_note = ("The synthetic logo was rendered by the actual 1000x200 PNG production renderer."
                  if banner_bytes else "The banner is an illustrative placeholder; the actual 1000x200 PNG renderer requires Pillow, which is unavailable in this run.")
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<title>PHX2 Telegram preview</title><style>
body{margin:0;background:#101820;color:#dfe9ef;font:15px/1.55 system-ui,sans-serif;padding:32px}
main{max-width:1180px;margin:auto}h1{font-size:28px}h2{font-size:17px}p{color:#9eb0bd}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:24px}
article{background:#182b39;border:1px solid #2a4252;border-radius:12px;overflow:hidden}
.caption{white-space:pre-wrap;padding:18px;font-size:14px;overflow-wrap:anywhere}
code{font:12px ui-monospace,monospace;color:#7bd3ee}.banner{width:100%;aspect-ratio:5;background:radial-gradient(ellipse at center,#356178,#172b39 70%);display:grid;place-items:center}
.banner span{height:70%;aspect-ratio:1;background:#55b9bb;border-radius:50%;display:grid;place-items:center;color:#10232d;font-size:12px;font-weight:800}
</style><main><h1>PHX2 Telegram presentation</h1>
<p>Offline review - all tokens and metrics are synthetic. ''' + image_note + '''
 Captions below come from the production formatters.</p>
<p>Discovery and PAPER events are distinct. Paper events are durably queued; delivery is disabled unless separately armed.</p>
<div class="grid">''' + "".join(cards) + "</div></main></html>"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-image", action="store_true")
    args = parser.parse_args()
    banner, status = synthetic_banner()
    if args.require_image and banner is None:
        raise SystemExit(status)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(preview_html(banner), encoding="utf-8")
    if banner is not None:
        args.output.with_suffix(".png").write_bytes(banner)
    print("Synthetic offline preview written. " + status)


if __name__ == "__main__":
    main()
