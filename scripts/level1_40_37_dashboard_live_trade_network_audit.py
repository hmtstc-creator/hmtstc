#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
NETWORK = ROOT / "frontend" / "js" / "components" / "liveTradeNetwork.js"
BOT = ROOT / "frontend" / "js" / "app" / "bot.js"
API = ROOT / "frontend" / "js" / "app" / "api.js"
RENDER = ROOT / "frontend" / "js" / "app" / "render.js"
CSS = ROOT / "frontend" / "css" / "dashboard-live-trade.css"
INDEX = ROOT / "frontend" / "index.html"
PRIOR = ROOT / "docs" / "LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT.md"


def _text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _all(text: str, values: list[str]) -> bool:
    return all(value in text for value in values)


def build_report() -> dict[str, Any]:
    dashboard = _text(DASHBOARD)
    network = _text(NETWORK)
    bot = _text(BOT)
    api = _text(API)
    render = _text(RENDER)
    css = _text(CSS)
    index = _text(INDEX)
    prior_status = json.loads(_text(PRIOR)).get("status")

    dashboard_forbidden_calls = [
        "/api/binance/market",
        "/api/coin-filter/test-scan",
        "/api/rules/auto-paper-lab",
        "scan_market",
    ]
    image_references = [".gif", ".jpg", ".jpeg", ".png", "background-image", "<img"]

    checks = {
        "dashboard_bot_controls_present": _all(dashboard, ["activateOpenMode()", "activateClosedMode()", "activateAutomaticMode()", "dashboard-emergency-stop"]),
        "header_bot_controls_not_required": 'const headerBotControls = "";' in render and "renderHeaderBotControls()" not in render,
        "live_trade_network_component_present": NETWORK.exists() and "HMTSTC_LIVE_TRADE_NETWORK" in network and "live-trade-network" in dashboard,
        "canvas_does_not_use_image_or_gif": "canvas" in network.lower() and not any(value in network.lower() for value in image_references),
        "canvas_request_animation_frame_present": "requestAnimationFrame" in network and "cancelAnimationFrame" in network,
        "canvas_animation_modes_present": _all(network, ["botRunning", "automatic", "const speed", "prefers-reduced-motion"]),
        "dashboard_bundle_endpoint_used": '"/api/dashboard/bundle"' in api,
        "dashboard_bot_status_endpoint_used": '"/api/bot/status"' in api and '"/api/bot/status"' in bot,
        "dashboard_last_scan_endpoint_used": '"/api/bot/last-scan"' in api,
        "dashboard_does_not_start_heavy_scan": not any(value in dashboard for value in dashboard_forbidden_calls),
        "start_200_avoids_generic_api_error": _all(bot, ["if ((result || {}).ok === false)", "Bot açıldı. Durum doğrulanıyor.", "Bot durumu kontrol ediliyor..."]),
        "mobile_responsive_css_present": "@media (max-width: 900px)" in css and "@media (max-width: 640px)" in css,
        "emergency_stop_dashboard_visible": _all(dashboard, ["Acil Stop", "HMTSTC_APP.set({modal:true})"]),
        "coinfilter_summary_dashboard_visible": _all(dashboard, ["Son Tarama Özeti", "Toplam görülen", "Liquidity", "Spread", "Strategy"]),
        "volume_diagnostic_supported": _all(dashboard, ["effective_min_quote_volume", "quoteVolume_USDT_24h", "USDT quote volume"]),
        "cached_network_source_priority_present": _all(dashboard, ["candidateRows", "passedRows", "const networkRows = scanRows;", "allowPlaceholder: false"]),
        "empty_network_message_present": "Henüz canlı tarama yok" in dashboard or "Filtreyi geçen coin yok" in dashboard,
        "component_assets_loaded": "./js/components/liveTradeNetwork.js" in index and "./css/dashboard-live-trade.css" in index,
        "prior_40_36_5_rev2_ok": prior_status == "ok",
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_40_36_5_rev2_status": prior_status,
        "blockers": blockers,
        "changed_scope": [
            "frontend/js/pages/dashboard.js",
            "frontend/js/components/liveTradeNetwork.js",
            "frontend/js/app/render.js",
            "frontend/css/dashboard-live-trade.css",
            "frontend/index.html",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.37 Dashboard Live Trade Network Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- Dashboard bot controls: `{_yn(report['dashboard_bot_controls_present'])}`",
        f"- Canvas component: `{_yn(report['live_trade_network_component_present'])}`",
        f"- Heavy scan cagrisi yok: `{_yn(report['dashboard_does_not_start_heavy_scan'])}`",
        f"- Mobil CSS: `{_yn(report['mobile_responsive_css_present'])}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    if report["blockers"]:
        lines.extend(f"- BLOCKER: {item}" for item in report["blockers"])
    else:
        lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Dashboard live trade network ve gomulu bot kontrol kalite kapisi temiz." if report["status"] == "ok" else "Dashboard live trade network kalite kapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = "LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_37_DASHBOARD_LIVE_TRADE_NETWORK_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"dashboard_bot_controls_present={str(report['dashboard_bot_controls_present']).lower()}")
    print(f"live_trade_network_component_present={str(report['live_trade_network_component_present']).lower()}")
    print(f"dashboard_does_not_start_heavy_scan={str(report['dashboard_does_not_start_heavy_scan']).lower()}")
    print(f"mobile_responsive_css_present={str(report['mobile_responsive_css_present']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
