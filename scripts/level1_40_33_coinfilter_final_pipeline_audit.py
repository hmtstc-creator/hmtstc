#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
SETTINGS_JS = ROOT / "frontend" / "js" / "app" / "settings.js"
BACKEND_CONFIG = ROOT / "backend" / "core" / "config.py"
ANALYSIS_SERVICE = ROOT / "backend" / "services" / "analysis_service.py"
BOT_ROUTES = ROOT / "backend" / "routes" / "bot_routes.py"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT.md"
PRIOR_AUDITS = [
    ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT.json",
]


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _section(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    if not end:
        return text[start_index:]
    end_index = text.find(end, start_index + len(start))
    return text[start_index:] if end_index < 0 else text[start_index:end_index]


def _contains_all(text: str, values: list[str]) -> bool:
    return all(value in text for value in values)


def build_report() -> dict[str, Any]:
    coin_filter_js = _load_text(COIN_FILTER_JS)
    settings_js = _load_text(SETTINGS_JS)
    backend_config = _load_text(BACKEND_CONFIG)
    analysis_service = _load_text(ANALYSIS_SERVICE)
    bot_routes = _load_text(BOT_ROUTES)
    render_section = _section(coin_filter_js, "return \"<div class='coin-filter-wrap", "")
    normalize_section = _section(settings_js, "normalizeCoinFilter: function", "normalizeSettings: function")
    test_scan_fn = _section(bot_routes, "def bot_coinfilter_test_scan", "@router.get(\"/last-scan\")")
    pipeline_fn = _section(analysis_service, "def build_coinfilter_pipeline", "def scan_market")
    prior_statuses = {
        path.stem.replace("LEVEL1_", "").replace("_AUDIT", ""): _load_json(path).get("status")
        for path in PRIOR_AUDITS
    }

    checks = {
        "coinfilter_page_no_active_filter_inventory": "Aktif Filtre Envanteri" not in render_section,
        "coinfilter_page_no_active_strategy_inventory": "Aktif Strateji Envanteri" not in render_section,
        "coinfilter_main_table_no_readonly_fixed_guard_rows": _contains_all(coin_filter_js, [
            "visibleConfigRows",
            "if (!item.editable) return false",
            "Sistem sabit korumaları",
        ]),
        "frontend_default_has_min_quote_volume": "min_quote_volume: 1000000" in settings_js,
        "frontend_default_has_min_trade_count": "min_trade_count: 1000" in settings_js,
        "backend_default_has_min_quote_volume": '"min_quote_volume": 1000000' in backend_config,
        "backend_default_has_min_trade_count": '"min_trade_count": 1000' in backend_config,
        "normalize_coinfilter_keeps_min_quote_volume": "min_quote_volume" in normalize_section and "source.min_quote_volume" in normalize_section,
        "normalize_coinfilter_keeps_min_trade_count": "min_trade_count" in normalize_section and "source.min_trade_count" in normalize_section,
        "coinfilter_test_scan_endpoint_present": '@router.get("/coinfilter-test-scan")' in bot_routes,
        "test_scan_does_not_require_bot_running": "bot_not_running" not in test_scan_fn and "data.get(\"bot_running\"" not in test_scan_fn,
        "test_scan_response_has_test_scan_true": 'scan["test_scan"] = True' in test_scan_fn,
        "test_scan_response_has_pipeline": "build_coinfilter_pipeline(scan, test_scan=True)" in test_scan_fn,
        "pipeline_has_all_contract_sections": _contains_all(pipeline_fn, [
            '"market_universe"',
            '"coinfilter"',
            '"strategy"',
            '"karabasan"',
            '"risk"',
            '"execution"',
            '"not_run_in_coinfilter_test"',
        ]),
        "coinfilter_page_has_new_funnel": _contains_all(coin_filter_js, [
            "CoinFilter Karar Hunisi",
            "Binance USDT Evreni",
            "Temel Guard",
            "CoinFilter Adayları",
        ]),
        "coinfilter_page_has_test_scan_button": _contains_all(coin_filter_js, [
            "Son Scan Verisini Yenile",
            "Test Scan Çalıştır",
            "/api/bot/coinfilter-test-scan",
        ]),
        "excluded_symbols_textarea_and_normalize_present": _contains_all(coin_filter_js + settings_js, [
            "normalizeExcludedSymbols",
            "<textarea",
            "excluded_symbols",
        ]),
        "previous_40_20_to_40_32_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Canli ortamda CoinFilter sayfasinda Rule/Strategy envanterinin gorunmedigini kontrol et.",
            "CoinFilter test scan endpointinin test_scan=true ve pipeline contract'i dondugunu dogrula.",
            "Paket 11'e gecmeden once CoinFilter aday havuzu ile bot karar hattini ayri kabul testlerinden gecir.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.33 CoinFilter Final Pipeline Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Rule envanteri yok: `{_yn(report['coinfilter_page_no_active_filter_inventory'])}`")
    lines.append(f"- Strategy envanteri yok: `{_yn(report['coinfilter_page_no_active_strategy_inventory'])}`")
    lines.append(f"- Test scan endpoint: `{_yn(report['coinfilter_test_scan_endpoint_present'])}`")
    lines.append(f"- Pipeline contract: `{_yn(report['pipeline_has_all_contract_sections'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key, value in report.items():
        if key.endswith("_present") or key.endswith("_ok") or key.startswith("coinfilter_") or key.startswith("frontend_") or key.startswith("backend_") or key.startswith("normalize_") or key.startswith("test_scan_") or key.startswith("pipeline_"):
            lines.append(f"- {key}: `{_yn(bool(value))}`")
    lines.append("")
    lines.append("## Blocker Listesi")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- BLOCKER: {blocker}")
    else:
        lines.append("Blocker yok.")
    lines.append("")
    lines.append("## Sonuc")
    lines.append("")
    lines.append("CoinFilter final sadeleştirme ve pipeline contract kalite kapisi temiz." if report["status"] == "ok" else "CoinFilter final pipeline kalite kapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT_OK",
        "blocker": "LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"coinfilter_test_scan_endpoint_present={str(report['coinfilter_test_scan_endpoint_present']).lower()}")
    print(f"test_scan_response_has_pipeline={str(report['test_scan_response_has_pipeline']).lower()}")
    print(f"pipeline_has_all_contract_sections={str(report['pipeline_has_all_contract_sections']).lower()}")
    print(f"previous_40_20_to_40_32_status_ok={str(report['previous_40_20_to_40_32_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
