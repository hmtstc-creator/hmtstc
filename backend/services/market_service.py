import json
import math
import threading
import time
from copy import deepcopy
from urllib.parse import urlencode
from urllib.request import urlopen

from core.config import BINANCE_SPOT_BASE_URL


_PUBLIC_CACHE: dict[str, tuple[float, object]] = {}
_PUBLIC_CACHE_LOCK = threading.RLock()
_PUBLIC_CACHE_MAX_ENTRIES = 256


def _finite_float(value, default=0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _finite_int(value, default=0) -> int:
    try:
        parsed = float(value)
        return int(parsed) if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _cache_key(path: str, params: dict) -> str:
    return f"{path}?{urlencode(sorted(params.items()))}"


def _read_cache(key: str):
    now = time.monotonic()
    with _PUBLIC_CACHE_LOCK:
        cached = _PUBLIC_CACHE.get(key)
        if not cached or cached[0] <= now:
            if cached:
                _PUBLIC_CACHE.pop(key, None)
            return None
        return deepcopy(cached[1])


def _write_cache(key: str, payload, ttl_seconds: float) -> None:
    if ttl_seconds <= 0:
        return
    with _PUBLIC_CACHE_LOCK:
        if len(_PUBLIC_CACHE) >= _PUBLIC_CACHE_MAX_ENTRIES:
            oldest_key = min(_PUBLIC_CACHE, key=lambda item: _PUBLIC_CACHE[item][0])
            _PUBLIC_CACHE.pop(oldest_key, None)
        _PUBLIC_CACHE[key] = (time.monotonic() + ttl_seconds, deepcopy(payload))


def request_binance_public(path: str, params: dict | None = None, timeout: float = 10, cache_ttl: float = 0):
    params = params or {}
    key = _cache_key(path, params)
    if cache_ttl > 0:
        cached = _read_cache(key)
        if cached is not None:
            return cached

    query = urlencode(params)
    url = f"{BINANCE_SPOT_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    bounded_timeout = max(0.1, min(float(timeout or 10), 10.0))
    with urlopen(url, timeout=bounded_timeout) as response:
        raw = response.read().decode("utf-8")
        payload = json.loads(raw) if raw else {}
    _write_cache(key, payload, cache_ttl)
    return payload


def normalize_binance_24h_ticker(item: dict, book_ticker: dict | None = None) -> dict:
    """Convert Binance public ticker fields into the canonical market row contract."""
    book_ticker = book_ticker if isinstance(book_ticker, dict) else {}
    symbol = str(item.get("symbol") or "").upper()
    price = _finite_float(item.get("lastPrice"))
    bid_price = _finite_float(book_ticker.get("bidPrice"))
    ask_price = _finite_float(book_ticker.get("askPrice"))
    midpoint = (bid_price + ask_price) / 2 if bid_price > 0 and ask_price >= bid_price else 0.0
    spread_percent = ((ask_price - bid_price) / midpoint * 100) if midpoint > 0 else None
    return {
        "symbol": symbol,
        "price": price,
        "last_price": price,
        "change_percent": _finite_float(item.get("priceChangePercent")),
        "volume": _finite_float(item.get("volume")),
        "quote_volume": _finite_float(item.get("quoteVolume")),
        "trade_count": _finite_int(item.get("count")),
        "weighted_avg_price": _finite_float(item.get("weightedAvgPrice")),
        "high_price": _finite_float(item.get("highPrice")),
        "low_price": _finite_float(item.get("lowPrice")),
        "bid_price": bid_price,
        "ask_price": ask_price,
        "spread_percent": round(spread_percent, 6) if spread_percent is not None else None,
        "market_data_source": "binance_spot_public",
        "ticker_24h_source": "binance_v3_ticker_24hr",
        "spread_source": "binance_v3_ticker_bookTicker" if spread_percent is not None else "unavailable",
        "quote_volume_basis": "quoteVolume_USDT_24h",
        "trade_count_basis": "count_24h",
    }


def binance_ping():
    url = f"{BINANCE_SPOT_BASE_URL}/v3/ping"
    with urlopen(url, timeout=10) as response:
        return {"status": "ok", "mode": "spot_testnet", "binance_response_code": response.status}


def get_current_price(symbol: str, timeout: float = 10) -> float:
    data = request_binance_public("/v3/ticker/price", {"symbol": symbol.upper()}, timeout=timeout, cache_ttl=1)
    return _finite_float(data.get("price"))


def get_symbol_price(symbol: str = "BTCUSDT"):
    data = request_binance_public("/v3/ticker/price", {"symbol": symbol.upper()}, cache_ttl=1)
    return {"status": "ok", "mode": "spot_testnet", "symbol": data.get("symbol"), "price": data.get("price")}


def fetch_klines(symbol: str, interval: str, limit: int, timeout: float = 10):
    return request_binance_public(
        "/v3/klines",
        {"symbol": symbol.upper(), "interval": interval, "limit": limit},
        timeout=timeout,
        cache_ttl=10,
    )


def get_market_symbols(limit: int = 500, settings: dict | None = None, strict: bool = True, timeout: float = 10):
    """Return the normalized Binance USDT spot universe."""
    started = time.monotonic()
    try:
        from services.coin_universe_service import build_coin_universe

        bounded_timeout = max(0.1, min(float(timeout or 10), 10.0))
        request_timeout = max(0.1, bounded_timeout / 2)
        ticker_rows = request_binance_public("/v3/ticker/24hr", timeout=request_timeout, cache_ttl=5)
        book_rows = request_binance_public("/v3/ticker/bookTicker", timeout=request_timeout, cache_ttl=3)
        if not isinstance(ticker_rows, list) or not isinstance(book_rows, list):
            raise ValueError("invalid_binance_market_payload")
        books_by_symbol = {
            str(row.get("symbol") or "").upper(): row
            for row in book_rows
            if isinstance(row, dict) and row.get("symbol")
        }
        usdt_symbols = [
            normalize_binance_24h_ticker(item, books_by_symbol.get(str(item.get("symbol") or "").upper()))
            for item in ticker_rows
            if isinstance(item, dict) and str(item.get("symbol") or "").upper().endswith("USDT")
        ]
        universe = build_coin_universe(usdt_symbols, settings=settings, limit=limit, strict=strict)
        return {
            "status": "ok", "mode": "spot_testnet", "live": True, "source": "binance", "strict": strict,
            "count": universe.get("count", 0), "total_seen": universe.get("total_seen", len(usdt_symbols)),
            "universe_rejected_count": universe.get("rejected_count", 0),
            "universe_rejection_breakdown": universe.get("rejection_breakdown", {}),
            "universe_rejection_breakdown_unique": universe.get("unique_rejection_breakdown", {}),
            "volume_rejection_diagnostics": universe.get("volume_rejection_diagnostics", {}),
            "market_data_contract": "binance_market_truth_v1",
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "symbols": universe.get("symbols", []), "error": None,
        }
    except Exception as error:
        return {
            "status": "error", "mode": "spot_testnet", "live": False, "source": "binance", "strict": strict,
            "count": 0, "total_seen": 0, "universe_rejected_count": 0,
            "universe_rejection_breakdown": {}, "universe_rejection_breakdown_unique": {},
            "volume_rejection_diagnostics": {}, "market_data_contract": "binance_market_truth_v1",
            "latency_ms": round((time.monotonic() - started) * 1000, 2), "symbols": [], "error": str(error),
        }


def get_binance_summary():
    symbol = "BTCUSDT"
    try:
        price = get_symbol_price(symbol)
        return {"status": "ok", "connected": True, "mode": "spot_testnet", "can_trade": False, "symbol": price.get("symbol"), "price": price.get("price")}
    except Exception as error:
        return {"status": "error", "connected": False, "mode": "spot_testnet", "can_trade": False, "symbol": symbol, "price": None, "error": str(error)}
