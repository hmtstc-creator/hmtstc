#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.indicators import macd  # noqa: E402
from services.analysis_service import analyze_symbol, calculate_volume_growth, scan_market  # noqa: E402


def kline_rows(interval: str) -> list:
    rows = []
    for index in range(80):
        close = 100 + (index * index * 0.002)
        quote_volume = 200 if index >= 76 else 100
        rows.append([index, close - 0.1, close + 0.5, close - 0.5, close, 1, index, quote_volume])
    return rows


def main() -> int:
    settings = {
        "coin_filter": {
            "min_quote_volume": 1000, "min_trade_count": 10, "min_volatility": 0.1,
            "volatility_interval": "15m", "volatility_candle_count": 12,
            "rsi_min_15m": 0, "rsi_max_15m": 100, "rsi_min_1h": 0, "rsi_max_1h": 100,
            "rsi_min_4h": 0, "rsi_max_4h": 100, "volume_growth_multiplier": 1.2,
            "lightweight_score_min": 0, "excluded_symbols": "",
        },
        "risk": {"max_spread_percent": 0.35, "take_profit": "2%"},
        "bot": {"scan_deep_analysis_limit": 1},
    }
    market_row = {
        "symbol": "TESTUSDT", "price": 112.5, "high_price": 114, "low_price": 100,
        "quote_volume": 10_000_000, "trade_count": 50_000, "change_percent": 2,
        "spread_percent": 0.05, "spread_source": "binance_v3_ticker_bookTicker",
    }
    with patch("services.analysis_service.fetch_klines", side_effect=lambda symbol, interval, limit, timeout=10: kline_rows(interval)):
        technical = analyze_symbol("TESTUSDT", settings, market_row=market_row)

    unavailable = calculate_volume_growth([100.0] * 10, 1.2)
    indicator = macd([100 + (index * index * 0.002) for index in range(80)])
    second_row = {**market_row, "symbol": "SECONDUSDT", "quote_volume": 5_000_000}
    market_payload = {
        "status": "ok", "live": True, "source": "binance", "count": 2, "total_seen": 2,
        "universe_rejected_count": 0, "universe_rejection_breakdown": {},
        "universe_rejection_breakdown_unique": {}, "volume_rejection_diagnostics": {},
        "symbols": [market_row, second_row],
    }
    deep_result = {**technical, "symbol": "TESTUSDT", "passed": True, "rejection_reasons": [], "reason": None}
    with (
        patch("services.analysis_service.get_market_symbols", return_value=market_payload),
        patch("services.analysis_service.analyze_symbol", return_value=deep_result) as analyze_mock,
    ):
        scan = scan_market(settings, limit=2, deep_analysis=True)

    analysis_text = (ROOT / "backend" / "services" / "analysis_service.py").read_text(encoding="utf-8")
    checks = {
        "rsi_is_real_multitimeframe": technical.get("technical_data_source") == "binance_klines" and all(technical.get(key) is not None for key in ("rsi_15m", "rsi_1h", "rsi_4h")),
        "ema_is_real_kline_signal": technical.get("ema_signal") is True and technical.get("technical_evaluated") is True,
        "macd_has_signal_and_histogram": indicator is not None and technical.get("macd") is not None and technical.get("macd_signal_value") is not None and technical.get("macd_histogram") is not None,
        "volume_growth_uses_equal_windows": technical.get("recent_volume") == 200 and technical.get("previous_volume_avg") == 100,
        "volume_growth_source_is_explicit": technical.get("volume_growth_source") == "binance_15m_kline_quote_volume" and technical.get("volume_growth_available") is True,
        "missing_volume_does_not_pass": unavailable["available"] is False and unavailable["passed"] is False and unavailable["reason"] == "insufficient_kline_quote_volume",
        "spread_is_not_hardcoded": technical.get("spread_percent") == 0.05 and technical.get("spread_source") == "binance_v3_ticker_bookTicker" and "spread_percent = 0.08" not in analysis_text,
        "lightweight_has_no_proxy_rsi": '"rsi_15m": None' in analysis_text and '"technical_data_source": "not_evaluated"' in analysis_text,
        "deep_analysis_is_limited": analyze_mock.call_count == 1 and scan.get("scan_diagnostics", {}).get("deep_analyzed_count") == 1,
        "only_deep_verified_row_is_candidate": scan.get("candidates_count") == 1 and any(row.get("reason") == "deep_analysis_limit_not_selected" for row in scan.get("scan_rows", [])),
        "deadlines_and_cancel_are_preserved": "deep_deadline" in analysis_text and "cancel_requested" in analysis_text,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("LEVEL1_40_45_PACKAGE_25_REAL_TECHNICAL_FILTER_BINDING_AUDIT_FAIL")
        print("failed=" + ",".join(failed))
        return 1
    print("LEVEL1_40_45_PACKAGE_25_REAL_TECHNICAL_FILTER_BINDING_AUDIT_OK")
    print("status=ok")
    print(f"checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
