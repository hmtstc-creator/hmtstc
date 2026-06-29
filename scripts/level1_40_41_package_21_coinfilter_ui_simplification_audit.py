#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
CSS = ROOT / "frontend" / "css" / "dashboard-funnel.css"


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    required = {
        "parameter_grid": "cf-parameter-grid" in page and ".cf-parameter-grid" in css,
        "save_button": "HMTSTC_COIN_FILTER_ACTIONS.save(event)" in page,
        "test_scan_button": "HMTSTC_COIN_FILTER_ACTIONS.runTestScan()" in page,
        "refresh_button": "HMTSTC_COIN_FILTER_ACTIONS.fetchLastScan()" in page,
        "max_spread_contract": 'section: "risk"' in page and 'key: "max_spread_percent"' in page,
        "max_spread_persistence_proof": "riskResponseMatches" in page and "riskRefreshMatches" in page,
        "ema_visible": 'name: "EMA Kontrolü"' in page,
        "macd_visible": 'name: "MACD Kontrolü"' in page,
        "quality_score_visible": 'key: "quality_score_min"' in page,
        "lightweight_score_visible": 'key: "lightweight_score_min"' in page,
        "excluded_symbols_visible": 'key: "excluded_symbols"' in page,
        "responsive_grid": "@media (max-width: 720px)" in css,
    }
    forbidden = {
        "system_guard_card": "Sistem Sabit Korumaları" in page,
        "rsi_period_row": "RSI Periyodu" in page,
        "volatility_timeframe_row": "Volatilite Timeframe" in page,
        "volatility_candle_row": "Volatilite Mum Sayısı" in page,
        "guard_info": "guardInfo" in page,
        "volume_diagnostic_card": "USDT Hacim Doğrulaması" in page,
        "rejection_diagnostic_cards": "Evren Eleme Sebepleri" in page or "Teknik Eleme Sebepleri" in page,
    }

    failures = [name for name, passed in required.items() if not passed]
    failures.extend(name for name, present in forbidden.items() if present)
    if failures:
        print("LEVEL1_40_41_PACKAGE_21_COINFILTER_UI_SIMPLIFICATION_AUDIT_FAIL")
        print("failed=" + ",".join(failures))
        return 1

    print("LEVEL1_40_41_PACKAGE_21_COINFILTER_UI_SIMPLIFICATION_AUDIT_OK")
    print("status=ok")
    print(f"required_checks={len(required)}")
    print(f"forbidden_checks={len(forbidden)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
