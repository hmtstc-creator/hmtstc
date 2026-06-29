#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PERFORMANCE = BACKEND / "services" / "performance_service.py"
ANALYSIS = BACKEND / "services" / "analysis_service.py"
QUALITY = BACKEND / "services" / "coin_quality_service.py"
COINFILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
NETWORK_JS = ROOT / "frontend" / "js" / "components" / "liveTradeNetwork.js"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_38_RUNTIME_DATETIME_COINFILTER_DASHBOARD_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_38_RUNTIME_DATETIME_COINFILTER_DASHBOARD_AUDIT.md"


def _text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path.relative_to(ROOT))
    return path.read_text(encoding="utf-8")


def _import_backend():
    sys.path.insert(0, str(BACKEND))
    from services.performance_service import build_dashboard_summary, seconds_between
    from services.analysis_service import _lightweight_analyze_market_row
    from services.coin_quality_service import score_coin_quality
    return build_dashboard_summary, seconds_between, _lightweight_analyze_market_row, score_coin_quality


def build_report() -> dict:
    build_dashboard_summary, seconds_between, lightweight, score_quality = _import_backend()
    perf = _text(PERFORMANCE)
    analysis = _text(ANALYSIS)
    quality = _text(QUALITY)
    coinfilter_js = _text(COINFILTER_JS)
    dashboard_js = _text(DASHBOARD_JS)
    network_js = _text(NETWORK_JS)

    settings = {
        "bot": {"max_open_positions": 5},
        "coin_filter": {
            "min_quote_volume": 1,
            "min_trade_count": 1,
            "min_volatility": 0,
            "rsi_min_15m": 0,
            "rsi_max_15m": 100,
            "rsi_min_1h": 0,
            "rsi_max_1h": 100,
            "rsi_min_4h": 0,
            "rsi_max_4h": 100,
            "volume_growth_multiplier": 1,
        },
    }
    data = {
        "bot_running": True,
        "bot_started_at": "2026-06-14T19:04:53.478371+00:00",
        "last_updated_at": "2026-06-14T22:09:43",
        "last_tick": "2026-06-14T22:09:43",
        "open_positions": [],
        "history": [
            {"pnl": "1.5", "entry_time": "2026-06-14T19:04:53+00:00", "exit_time": "2026-06-14T22:09:43"},
            {"pnl": "bad", "entry_time": None, "exit_time": None},
        ],
        "last_scan": {"status": "ok", "time": "2026-06-14T22:09:43", "candidates_count": 0, "scan_rows": []},
        "performance_points": [{"time": "2026-06-14T19:04:53.478371+00:00", "wallet_value": "1000"}],
        "logs": [],
    }
    dashboard = build_dashboard_summary(data, settings)
    row = lightweight({
        "symbol": "TESTUSDT",
        "price": "1",
        "lastPrice": "1",
        "high_price": "1.1",
        "low_price": "0.9",
        "quote_volume": "1000",
        "trade_count": "10",
        "change_percent": "1",
        "weighted_avg_price": "1",
    }, settings)
    quality_probe = score_quality({"symbol": "TESTUSDT", "quote_volume": 1000, "volatility": 2, "spread_percent": 0.05}, min_quote_volume=1)

    checks = {
        "seconds_between_mixed_timezone_safe": seconds_between("2026-06-14T19:04:53.478371+00:00", "2026-06-14T22:09:43") > 0,
        "dashboard_summary_mixed_timezone_safe": dashboard.get("runtime_seconds", 0) > 0 and dashboard.get("total_trades") == 2,
        "parse_dt_normalizes_timezone": "timezone.utc" in perf and "astimezone(timezone.utc)" in perf,
        "get_trade_stats_safe_pnl": "def _position_pnl" in perf,
        "quality_uses_configured_min_quote_volume": "configured_min_quote_volume" in quality and "quote_volume < configured_min_quote_volume" in quality,
        "analysis_passes_min_quote_volume_to_quality": "min_quote_volume=cfg[\"min_quote_volume\"]" in analysis and "min_quote_volume=filter_config[\"min_quote_volume\"]" in analysis,
        "low_liquidity_not_for_min_volume_one": "low_liquidity" not in (row.get("rejection_reasons") or []) and "low_liquidity" not in (quality_probe.get("reasons") or []),
        "coinfilter_input_supports_k_m_b": "raw.endsWith(\"k\")" in coinfilter_js and "raw.endsWith(\"m\")" in coinfilter_js and "raw.endsWith(\"b\")" in coinfilter_js,
        "coinfilter_row_rejection_count_column": "Son Scan Elenen" in coinfilter_js and "rejectionCountCell(item)" in coinfilter_js,
        "coinfilter_merges_universe_and_technical_breakdown": "mergedRejectionBreakdown" in coinfilter_js and "scan.universe_rejection_breakdown" in coinfilter_js and "scan.rejection_breakdown" in coinfilter_js,
        "dashboard_network_uses_passed_only": "candidateRows" in dashboard_js and "passedRows" in dashboard_js and "const networkRows = scanRows;" in dashboard_js,
        "dashboard_network_no_market_fallback": "marketRows" not in dashboard_js[dashboard_js.find("const candidateRows"):dashboard_js.find("setTimeout(function ()", dashboard_js.find("const candidateRows"))],
        "network_placeholder_can_be_disabled": "allowPlaceholder !== false" in network_js and "allowPlaceholder: false" in dashboard_js,
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "dashboard_runtime_seconds": dashboard.get("runtime_seconds"),
        "lightweight_rejection_reasons_min_1": row.get("rejection_reasons"),
        "quality_reasons_min_1": quality_probe.get("reasons"),
        "blockers": blockers,
    }


def write_outputs(report: dict) -> None:
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Level1 40.38 Runtime Datetime CoinFilter Dashboard Audit",
        "",
        f"- Durum: `{report['status']}`",
        f"- Runtime seconds: `{report.get('dashboard_runtime_seconds')}`",
        f"- Min volume=1 rejection reasons: `{report.get('lightweight_rejection_reasons_min_1')}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report["checks"].items():
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
        write_outputs(report)
    except Exception as exc:
        print(f"LEVEL1_40_38_RUNTIME_DATETIME_COINFILTER_DASHBOARD_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_38_RUNTIME_DATETIME_COINFILTER_DASHBOARD_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_38_RUNTIME_DATETIME_COINFILTER_DASHBOARD_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
