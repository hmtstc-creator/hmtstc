#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "dashboard_routes": ROOT / "backend" / "routes" / "dashboard_routes.py",
    "rule_engine": ROOT / "backend" / "services" / "rule_engine.py",
    "api_js": ROOT / "frontend" / "js" / "app" / "api.js",
    "coinfilter_js": ROOT / "frontend" / "js" / "pages" / "coinFilter.js",
    "dashboard_js": ROOT / "frontend" / "js" / "pages" / "dashboard.js",
}
JSON_OUT = ROOT / "docs" / "LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT.md"


def text(name: str) -> str:
    path = FILES[name]
    if not path.exists():
        raise FileNotFoundError(path.relative_to(ROOT))
    return path.read_text(encoding="utf-8")


def section(source: str, start_marker: str, end_marker: str | None = None) -> str:
    start = source.find(start_marker)
    if start < 0:
        return ""
    if not end_marker:
        return source[start:]
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        return source[start:]
    return source[start:end]


def build_report() -> dict:
    dashboard_routes = text("dashboard_routes")
    rule_engine = text("rule_engine")
    api_js = text("api_js")
    coinfilter_js = text("coinfilter_js")
    dashboard_js = text("dashboard_js")

    heavy_sync = section(api_js, "syncHeavyApiData: async function", "}\n};")
    rule_status_fn = section(rule_engine, "def build_rule_store_status", "\n\ndef save_rule_store")
    coinfilter_page = section(coinfilter_js, "window.HMTSTC_PAGES.coinFilter = function", None)
    dashboard_page = section(dashboard_js, "window.HMTSTC_PAGES.dashboard = function", None)

    checks = {
        "dashboard_bundle_includes_bot_scan": '"botScan": build_cached_last_scan_payload(user, data' in dashboard_routes,
        "dashboard_bundle_uses_lightweight_rules": 'list_rules(user, include_store_status=False)' in dashboard_routes,
        "dashboard_cached_scan_has_filter_counts": '"filter_rejection_counts": filter_counts' in dashboard_routes,
        "dashboard_cached_scan_has_time_aliases": '"scan_time": last_scan.get("time")' in dashboard_routes and '"last_scan_at": last_scan.get("time")' in dashboard_routes,
        "api_applies_bundle_bot_scan": "if (bundled.botScan)" in api_js and "HMTSTC_DATA.botScan = bundled.botScan" in api_js,
        "api_heavy_sync_no_market_fetch": "/api/binance/market" not in heavy_sync,
        "api_heavy_sync_keeps_last_scan_fetch": "/api/bot/last-scan" in heavy_sync,
        "coinfilter_has_scan_normalizer": "function normalizeCoinFilterScanPayload" in coinfilter_js,
        "coinfilter_page_uses_normalized_scan": "const scan = normalizeCoinFilterScanPayload(data.botScan || {});" in coinfilter_js,
        "coinfilter_has_cached_scan_robust": "Object.keys(scan.filter_rejection_counts || {}).length" in coinfilter_js and "scan.candidates_count" in coinfilter_js,
        "coinfilter_row_counts_direct_keyed": "Object.prototype.hasOwnProperty.call(directCounts, key)" in coinfilter_js,
        "coinfilter_test_scan_manual_only": "onclick='HMTSTC_COIN_FILTER_ACTIONS.runTestScan()'" in coinfilter_js and "runTestScan()" not in coinfilter_page.split("onclick='HMTSTC_COIN_FILTER_ACTIONS.runTestScan()'")[0],
        "dashboard_network_passed_true_only": "return row && row.passed === true;" in dashboard_js,
        "dashboard_page_uses_normalized_scan": "const scan = normalizeDashboardScan(data().botScan || {});" in dashboard_js,
        "rule_store_status_default_no_deep_backup_scan": "def build_rule_store_status(username: str | None = None, *, deep: bool = False)" in rule_engine,
        "runtime_backup_rglob_guarded_by_deep": "if deep:" in rule_status_fn and "RUNTIME_BACKUPS_DIR.rglob" in rule_status_fn and rule_status_fn.find("if deep:") < rule_status_fn.find("RUNTIME_BACKUPS_DIR.rglob"),
    }
    blockers = [key for key, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "blockers": blockers,
    }


def write_md(report: dict) -> None:
    lines = [
        "# Level1 40.39.2 CoinFilter Single Source Hydration Audit",
        "",
        f"- Durum: `{report['status']}`",
        "- Amaç: CoinFilter ve Dashboard açılışta cached `last_scan` verisini tek kaynak olarak okusun; test scan manuel kalsın; dashboard bundle ağır rule backup scan yapmasın.",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{'evet' if value else 'hayir'}`")
    lines.extend(["", "## Blocker", ""])
    if report["blockers"]:
        lines.extend(f"- {item}" for item in report["blockers"])
    else:
        lines.append("Blocker yok.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_md(report)
    except Exception as exc:
        print(f"LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"dashboard_bundle_includes_bot_scan={str(report['dashboard_bundle_includes_bot_scan']).lower()}")
    print(f"coinfilter_row_counts_direct_keyed={str(report['coinfilter_row_counts_direct_keyed']).lower()}")
    print(f"api_heavy_sync_no_market_fetch={str(report['api_heavy_sync_no_market_fetch']).lower()}")
    print(f"dashboard_network_passed_true_only={str(report['dashboard_network_passed_true_only']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
