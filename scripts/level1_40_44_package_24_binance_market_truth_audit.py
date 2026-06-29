#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.coin_universe_service import build_coin_universe, is_leveraged_token  # noqa: E402
from services.market_service import get_market_symbols, normalize_binance_24h_ticker  # noqa: E402


def main() -> int:
    ticker = {
        "symbol": "BTCUSDT", "lastPrice": "65000.5", "priceChangePercent": "1.25",
        "volume": "10", "quoteVolume": "650005", "count": "3210",
        "weightedAvgPrice": "64900", "highPrice": "66000", "lowPrice": "64000",
    }
    book = {"symbol": "BTCUSDT", "bidPrice": "65000", "askPrice": "65001"}
    normalized = normalize_binance_24h_ticker(ticker, book)
    universe = build_coin_universe(
        [normalized, normalize_binance_24h_ticker({**ticker, "symbol": "USDCUSDT"}, book)],
        settings={"coin_filter": {"min_quote_volume": 100, "min_trade_count": 10}},
        strict=True,
    )
    calls = []

    def fake_request(path, params=None, timeout=10, cache_ttl=0):
        calls.append((path, cache_ttl, timeout))
        return [ticker] if path.endswith("24hr") else [book]

    with patch("services.market_service.request_binance_public", side_effect=fake_request):
        market = get_market_symbols(
            limit=10,
            settings={"coin_filter": {"min_quote_volume": 100, "min_trade_count": 10}},
            strict=True,
            timeout=3,
        )

    market_text = (ROOT / "backend" / "services" / "market_service.py").read_text(encoding="utf-8")
    route_text = (ROOT / "backend" / "routes" / "binance_routes.py").read_text(encoding="utf-8")
    checks = {
        "canonical_numeric_fields": normalized["price"] == 65000.5 and normalized["quote_volume"] == 650005 and normalized["trade_count"] == 3210,
        "real_book_spread": 0 < normalized["spread_percent"] < 0.01 and normalized["spread_source"] == "binance_v3_ticker_bookTicker",
        "truth_source_labels": normalized["quote_volume_basis"] == "quoteVolume_USDT_24h" and normalized["trade_count_basis"] == "count_24h",
        "stable_guard_backend": universe["rejected_count"] == 1 and universe["unique_rejection_breakdown"].get("stable_pair") == 1,
        "leveraged_guard_does_not_reject_jup": is_leveraged_token("BTCUPUSDT") and not is_leveraged_token("JUPUSDT"),
        "market_uses_two_public_truth_feeds": [call[0] for call in calls] == ["/v3/ticker/24hr", "/v3/ticker/bookTicker"],
        "market_contract_exposed": market.get("market_data_contract") == "binance_market_truth_v1" and market.get("symbols", [])[0]["quote_volume"] == 650005,
        "bounded_cache_present": "_PUBLIC_CACHE_MAX_ENTRIES = 256" in market_text and "cache_ttl=10" in market_text,
        "timeouts_are_bounded": "max(0.1, min(float(timeout or 10), 10.0))" in market_text,
        "route_uses_market_service": "get_market_symbols" in route_text and 'prefix="/api/binance"' in route_text,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("LEVEL1_40_44_PACKAGE_24_BINANCE_MARKET_TRUTH_AUDIT_FAIL")
        print("failed=" + ",".join(failed))
        return 1
    print("LEVEL1_40_44_PACKAGE_24_BINANCE_MARKET_TRUTH_AUDIT_OK")
    print("status=ok")
    print(f"checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
