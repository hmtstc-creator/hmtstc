#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ANALYSIS_SERVICE = BACKEND / "services" / "analysis_service.py"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT.md"
PRIOR_AUDITS = [
    ROOT / "docs" / f"LEVEL1_40_{number}_{name}_AUDIT.json"
    for number, name in [
        (20, "LIVE_STARTUP_RULES_HYDRATION"),
        (21, "AUTH_RESTORE_TRUTH"),
        (22, "COINFILTER_RULES_PAPERLAB"),
        (23, "RULES_PAPERLAB_INDEPENDENCE"),
        (24, "PAPERLAB_AUTONOMOUS_ENGINE"),
        (25, "PAPERLAB_PERSISTENCE"),
        (26, "PAPERLAB_HYDRATION_STABILITY"),
        (27, "RUNTIME_HEALTH_PAPERLAB_STORE"),
        (28, "RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION"),
        (29, "COINFILTER_PERSISTENCE_AND_8H_REPORT"),
        (30, "BOT_RUNTIME_HEARTBEAT_TRUTH"),
        (31, "BOT_RESTORE_REAL_LOOP"),
        (32, "BOT_RESTORE_FIRST_TICK"),
        (33, "COINFILTER_FINAL_PIPELINE"),
    ]
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
    end_index = text.find(end, start_index + len(start))
    return text[start_index:] if end_index < 0 else text[start_index:end_index]


def _runtime_lightweight_probe() -> dict[str, Any]:
    sys.path.insert(0, str(BACKEND))
    service = importlib.import_module("services.analysis_service")
    original_market = service.get_market_symbols
    original_analyze = service.analyze_symbol
    analyze_calls = 0

    def fake_market(*, limit: int, settings: dict, strict: bool) -> dict:
        return {
            "status": "ok",
            "live": True,
            "count": 1,
            "total_seen": 1,
            "universe_rejected_count": 0,
            "universe_rejection_breakdown": {},
            "symbols": [{
                "symbol": "BTCUSDT",
                "price": "60000",
                "quote_volume": 500000000,
                "trade_count": 250000,
                "change_percent": 1.2,
            }],
        }

    def forbidden_analyze(symbol: str, settings: dict) -> dict:
        nonlocal analyze_calls
        analyze_calls += 1
        raise AssertionError(f"analyze_symbol called for {symbol}")

    try:
        service.get_market_symbols = fake_market
        service.analyze_symbol = forbidden_analyze
        result = service.scan_market({}, limit=20, deep_analysis=False)
    finally:
        service.get_market_symbols = original_market
        service.analyze_symbol = original_analyze

    diagnostics = result.get("scan_diagnostics") or {}
    return {
        "analyze_calls": analyze_calls,
        "status": result.get("status"),
        "mode": diagnostics.get("mode"),
        "deep_analysis_enabled": diagnostics.get("deep_analysis_enabled"),
        "deep_analysis_limit": diagnostics.get("deep_analysis_limit"),
        "deep_analyzed_count": diagnostics.get("deep_analyzed_count"),
    }


def build_report() -> dict[str, Any]:
    analysis_service = _load_text(ANALYSIS_SERVICE)
    bot_routes = _load_text(BOT_ROUTES)
    coin_filter_js = _load_text(COIN_FILTER_JS)
    scan_fn = _section(analysis_service, "def scan_market", "def scan_debug")
    test_scan_fn = _section(bot_routes, "def bot_coinfilter_test_scan", '@router.get("/last-scan")')
    frontend_fn = _section(coin_filter_js, "runTestScan: async function", "\n};")
    prior_statuses = {path.stem: _load_json(path).get("status") for path in PRIOR_AUDITS}
    probe = _runtime_lightweight_probe()

    checks = {
        "test_scan_uses_deep_analysis_false": "scan_market(settings, limit=limit, deep_analysis=False)" in test_scan_fn,
        "scan_market_accepts_deep_analysis_parameter": "def scan_market(settings: dict, limit: int = 1000, *, deep_analysis: bool = True" in analysis_service,
        "deep_analysis_false_skips_analyze_symbol": probe["analyze_calls"] == 0,
        "deep_analysis_false_skips_fetch_klines": probe["analyze_calls"] == 0 and "fetch_klines(" not in scan_fn,
        "test_scan_response_has_test_scan_true": 'scan["test_scan"] = True' in test_scan_fn,
        "test_scan_response_has_pipeline": "build_coinfilter_pipeline(scan, test_scan=True)" in test_scan_fn,
        "diagnostics_deep_analysis_disabled": probe["deep_analysis_enabled"] is False,
        "diagnostics_deep_analysis_limit_zero": probe["deep_analysis_limit"] == 0,
        "diagnostics_deep_analyzed_count_zero": probe["deep_analyzed_count"] == 0,
        "diagnostics_lightweight_mode_present": probe["mode"] == "coinfilter_lightweight_test_scan",
        "frontend_test_scan_loading_present": "Test scan çalışıyor..." in frontend_fn,
        "frontend_timeout_message_present": "Test scan zaman aşımına uğradı. Deep analiz kapalı olmalı; backend kontrol edin." in frontend_fn,
        "previous_40_20_to_40_33_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "runtime_probe": probe,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Deploy sonrasi limit=20 ve limit=1000 CoinFilter test scan surelerini olc.",
            "Test scan diagnostics icinde deep_analysis_enabled=false ve deep_analyzed_count=0 oldugunu dogrula.",
            "Nginx timeout degerini artirmadan canli 504 sonucunun temizlendigini kontrol et.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.34 CoinFilter Test Scan Timeout Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- Test scan deep analysis kapali: `{_yn(report['test_scan_uses_deep_analysis_false'])}`",
        f"- Runtime analyze_symbol call count: `{report['runtime_probe']['analyze_calls']}`",
        f"- Lightweight mode: `{report['runtime_probe']['mode']}`",
        f"- Onceki 40.20-40.33 zinciri: `{_yn(report['previous_40_20_to_40_33_status_ok'])}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    if report["blockers"]:
        lines.extend(f"- BLOCKER: {blocker}" for blocker in report["blockers"])
    else:
        lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("CoinFilter test scan lightweight kalite kapisi temiz." if report["status"] == "ok" else "CoinFilter test scan timeout kalite kapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT_OK",
        "blocker": "LEVEL1_40_34_COINFILTER_TEST_SCAN_TIMEOUT_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"test_scan_uses_deep_analysis_false={str(report['test_scan_uses_deep_analysis_false']).lower()}")
    print(f"deep_analysis_false_skips_analyze_symbol={str(report['deep_analysis_false_skips_analyze_symbol']).lower()}")
    print(f"diagnostics_deep_analysis_disabled={str(report['diagnostics_deep_analysis_disabled']).lower()}")
    print(f"previous_40_20_to_40_33_status_ok={str(report['previous_40_20_to_40_33_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
