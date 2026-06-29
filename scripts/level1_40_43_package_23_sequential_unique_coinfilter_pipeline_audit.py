#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.analysis_service import (  # noqa: E402
    COINFILTER_REJECTION_ORDER,
    build_filter_rejection_counts,
    build_unique_filter_rejection_counts,
    first_rejection_reason,
)
from services.coin_universe_service import build_coin_universe  # noqa: E402


def main() -> int:
    rows = [
        {"symbol": "A", "passed": False, "rejection_reasons": ["score_below_threshold", "low_quote_volume"]},
        {"symbol": "B", "passed": False, "rejection_reasons": ["macd_negative", "low_volatility", "wide_spread"]},
        {"symbol": "C", "passed": False, "first_rejection_reason": "excluded_symbol", "rejection_reasons": ["excluded_symbol"]},
        {"symbol": "D", "passed": True, "rejection_reasons": []},
    ]
    for row in rows:
        if row.get("passed") is not True and not row.get("first_rejection_reason"):
            row["first_rejection_reason"] = first_rejection_reason(row.get("rejection_reasons"))
    unique = build_unique_filter_rejection_counts(rows, {})
    cumulative = build_filter_rejection_counts({}, {"score_below_threshold": 1, "low_quote_volume": 1, "macd_negative": 1, "low_volatility": 1, "wide_spread": 1, "excluded_symbol": 1})
    universe = build_coin_universe([
        {"symbol": "USDCUSDT", "lastPrice": "1", "quoteVolume": "1", "count": "1"},
        {"symbol": "LOWUSDT", "lastPrice": "1", "quoteVolume": "1", "count": "1"},
        {"symbol": "TRADEUSDT", "lastPrice": "1", "quoteVolume": "1000", "count": "1"},
    ], settings={"coin_filter": {"min_quote_volume": 100, "min_trade_count": 10}}, strict=True)
    unique_with_universe = build_unique_filter_rejection_counts([], universe.get("unique_rejection_breakdown"))
    analysis = (ROOT / "backend" / "services" / "analysis_service.py").read_text(encoding="utf-8")
    routes = (ROOT / "backend" / "routes" / "bot_routes.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "js" / "pages" / "coinFilter.js").read_text(encoding="utf-8")

    checks = {
        "order_is_fixed": COINFILTER_REJECTION_ORDER == ("low_quote_volume", "low_liquidity", "low_trade_count", "low_volatility", "wide_spread", "weak_volume_growth", "rsi_out_of_range", "ema_not_aligned", "macd_negative", "low_quality_score", "score_below_threshold", "excluded_symbol"),
        "volume_wins_over_score": rows[0]["first_rejection_reason"] == "low_quote_volume",
        "volatility_wins_over_spread_macd": rows[1]["first_rejection_reason"] == "low_volatility",
        "unique_total_matches_rejected_rows": sum(unique.values()) == 3,
        "unique_counts_are_first_failure_only": unique["min_quote_volume"] == 1 and unique["min_volatility"] == 1 and unique["excluded_symbols"] == 1 and unique["lightweight_score_min"] == 0,
        "cumulative_is_separate": cumulative["lightweight_score_min"] == 1 and cumulative["max_spread_percent"] == 1 and cumulative["macd_rule"] == 1,
        "universe_rejections_are_unique": sum(universe.get("unique_rejection_breakdown", {}).values()) == universe.get("rejected_count") == 3,
        "universe_first_failure_counts": unique_with_universe["stable_pair_guard"] == 1 and unique_with_universe["min_quote_volume"] == 1 and unique_with_universe["min_trade_count"] == 1,
        "scan_rows_expose_first_reason": '"first_rejection_reason"' in analysis,
        "payload_has_cumulative_field": '"filter_rejection_counts_cumulative"' in analysis and '"filter_rejection_counts_cumulative"' in routes,
        "ui_uses_direct_unique_counts": "const directCounts = (scan.filter_rejection_counts" in frontend and "return 0;" in frontend,
        "ui_shows_first_reason": "row.first_rejection_reason" in frontend,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("LEVEL1_40_43_PACKAGE_23_SEQUENTIAL_UNIQUE_COINFILTER_PIPELINE_AUDIT_FAIL")
        print("failed=" + ",".join(failed))
        return 1
    print("LEVEL1_40_43_PACKAGE_23_SEQUENTIAL_UNIQUE_COINFILTER_PIPELINE_AUDIT_OK")
    print("status=ok")
    print(f"checks={len(checks)}")
    print(f"unique_rejected={sum(unique.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
