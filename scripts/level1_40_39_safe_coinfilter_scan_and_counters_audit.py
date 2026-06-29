#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
ANALYSIS = BACKEND / "services" / "analysis_service.py"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
NETWORK_JS = ROOT / "frontend" / "js" / "components" / "liveTradeNetwork.js"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_39_SAFE_COINFILTER_SCAN_AND_COUNTERS_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_39_SAFE_COINFILTER_SCAN_AND_COUNTERS_AUDIT.md"


def text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def bool_text(value: bool) -> str:
    return "evet" if value else "hayir"


def probe_coinfilter_math() -> dict:
    sys.path.insert(0, str(BACKEND))
    from services.analysis_service import _lightweight_analyze_market_row, build_filter_rejection_counts

    settings = {
        "coin_filter": {
            "min_quote_volume": 1,
            "min_trade_count": 1,
            "min_volatility": 0,
            "volume_growth_multiplier": 1,
            "lightweight_score_min": 55,
        }
    }
    row = _lightweight_analyze_market_row(
        {
            "symbol": "AAAUSDT",
            "price": "1",
            "lastPrice": "1",
            "quote_volume": "1",
            "quoteVolume": "1",
            "trade_count": "1",
            "count": "1",
            "high_price": "1.01",
            "low_price": "0.99",
            "weighted_avg_price": "1",
            "change_percent": "0",
        },
        settings,
    )
    reasons = row.get("rejection_reasons") or []
    counts = build_filter_rejection_counts(
        {"low_quote_volume": 2, "stable_pair": 1},
        {"score_below_threshold": 3, "rsi_out_of_range": 4},
    )
    return {
        "low_volume_not_forced_when_user_min_is_1": "low_quote_volume" not in reasons and "low_liquidity" not in reasons,
        "low_trade_not_forced_when_user_min_is_1": "low_trade_count" not in reasons,
        "score_below_threshold_counted": "score_below_threshold" in reasons,
        "counter_min_quote_volume": counts.get("min_quote_volume"),
        "counter_lightweight_score_min": counts.get("lightweight_score_min"),
        "counter_rsi_min_15m": counts.get("rsi_min_15m"),
        "row_reasons": reasons,
    }


def build_report() -> dict:
    bot_routes = text(BOT_ROUTES)
    analysis = text(ANALYSIS)
    coin_filter_js = text(COIN_FILTER_JS)
    dashboard_js = text(DASHBOARD_JS)
    network_js = text(NETWORK_JS)
    probe = probe_coinfilter_math()

    checks = {
        "coinfilter_test_scan_has_safe_cap": "COINFILTER_TEST_SCAN_MAX_LIMIT = 350" in bot_routes and "min(requested_limit, COINFILTER_TEST_SCAN_MAX_LIMIT)" in bot_routes,
        "coinfilter_test_scan_has_lock": "_COINFILTER_TEST_SCAN_LOCKS" in bot_routes and "lock.acquire(blocking=False)" in bot_routes,
        "coinfilter_test_scan_has_cooldown_cache": "COINFILTER_TEST_SCAN_COOLDOWN_SECONDS" in bot_routes and "safe_scan_cache_hit" in bot_routes,
        "coinfilter_test_scan_has_timeout": "timeout_seconds=COINFILTER_TEST_SCAN_TIMEOUT_SECONDS" in bot_routes,
        "coinfilter_test_scan_deep_analysis_false": "deep_analysis=False" in bot_routes,
        "score_below_threshold_added_to_reasons": "_add_reason(reasons, \"score_below_threshold\")" in analysis,
        "lightweight_score_min_configurable": "lightweight_score_min" in analysis and "coin_filter.get(\"lightweight_score_min\"" in analysis,
        "filter_rejection_counts_backend_present": "build_filter_rejection_counts" in analysis and "filter_rejection_counts" in analysis and "filter_rejection_counts" in bot_routes,
        "coinfilter_page_uses_row_key_counters": "rejectionCountForRow" in coin_filter_js and "filter_rejection_counts" in coin_filter_js and "item.key" in coin_filter_js,
        "coinfilter_page_caps_test_scan": "Math.min(Number(requestedLimit) || 200, 350)" in coin_filter_js,
        "coinfilter_page_lightweight_score_editable": "data-cf-key" in coin_filter_js and "lightweight_score_min" in coin_filter_js and "editable: true" in coin_filter_js,
        "dashboard_network_only_passed_candidates": ("row.passed === true" in dashboard_js or "row.passed !== false" in dashboard_js) and "Filtreyi geçen coin yok" in dashboard_js,
        "network_animation_does_not_hard_reset_on_every_mount": "previous.options = options || {}" in network_js and "existingMap" in network_js,
        "network_still_has_request_animation_frame_and_cancel": "requestAnimationFrame" in network_js and "cancelAnimationFrame" in network_js,
        "probe_low_volume_user_min_1_ok": probe["low_volume_not_forced_when_user_min_is_1"],
        "probe_low_trade_user_min_1_ok": probe["low_trade_not_forced_when_user_min_is_1"],
        "probe_score_below_threshold_counted": probe["score_below_threshold_counted"],
        "probe_counter_mapping_ok": probe["counter_min_quote_volume"] == 2 and probe["counter_lightweight_score_min"] == 3 and probe["counter_rsi_min_15m"] == 4,
    }
    blockers = [f"{k}=false" for k, v in checks.items() if not v]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "probe": probe,
        "blockers": blockers,
    }


def write_markdown(report: dict) -> None:
    lines = [
        "# Level1 40.39 Safe CoinFilter Scan and Counters Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- Test scan CPU-safe cap/lock/cache: `{bool_text(report['coinfilter_test_scan_has_safe_cap'] and report['coinfilter_test_scan_has_lock'] and report['coinfilter_test_scan_has_cooldown_cache'])}`",
        f"- Satir bazli CoinFilter sayaclari: `{bool_text(report['coinfilter_page_uses_row_key_counters'])}`",
        f"- Min volume=1 iken low liquidity zorlanmiyor: `{bool_text(report['probe_low_volume_user_min_1_ok'])}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{bool_text(value)}`")
    lines += ["", "## Blocker", ""]
    lines.append("Blocker yok." if not report["blockers"] else "\n".join(f"- {b}" for b in report["blockers"]))
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_39_SAFE_COINFILTER_SCAN_AND_COUNTERS_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_39_SAFE_COINFILTER_SCAN_AND_COUNTERS_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_39_SAFE_COINFILTER_SCAN_AND_COUNTERS_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"coinfilter_test_scan_has_safe_cap={str(report['coinfilter_test_scan_has_safe_cap']).lower()}")
    print(f"coinfilter_page_uses_row_key_counters={str(report['coinfilter_page_uses_row_key_counters']).lower()}")
    print(f"probe_low_volume_user_min_1_ok={str(report['probe_low_volume_user_min_1_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
