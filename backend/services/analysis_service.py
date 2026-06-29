from __future__ import annotations

import time
import math

from collections import Counter
from datetime import datetime
from statistics import mean
from uuid import uuid4

from core.config import DEFAULT_COIN_FILTER
from core.indicators import ema, macd as calculate_macd, rsi, to_float
from services.coin_quality_service import score_coin_quality
from services.market_service import fetch_klines, get_market_symbols


def _safe_float(value, fallback=0.0):
    try:
        if isinstance(value, str):
            raw = value.strip().lower().replace("usdt", "").replace("usd", "").replace("$", "").replace(" ", "")
            multiplier = 1.0
            if raw.endswith("k"):
                multiplier = 1_000.0
                raw = raw[:-1]
            elif raw.endswith("m"):
                multiplier = 1_000_000.0
                raw = raw[:-1]
            elif raw.endswith("b"):
                multiplier = 1_000_000_000.0
                raw = raw[:-1]
            if "," in raw and "." not in raw:
                decimal_part = raw.rsplit(",", 1)[-1]
                raw = raw.replace(",", "") if len(decimal_part) == 3 else raw.replace(",", ".")
            else:
                raw = raw.replace(",", "")
            parsed = float(raw) * multiplier
        else:
            parsed = float(value)
        return parsed if math.isfinite(parsed) else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_int(value, fallback=0):
    try:
        parsed = float(value)
        return int(parsed) if math.isfinite(parsed) else fallback
    except (TypeError, ValueError):
        return fallback


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason and reason not in reasons:
        reasons.append(reason)


def _merge_breakdowns(*sources: dict | None) -> Counter:
    merged = Counter()
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            merged[str(key)] += _safe_int(value, 0)
    return merged


COINFILTER_REJECTION_ORDER = (
    "low_quote_volume",
    "low_liquidity",
    "low_trade_count",
    "low_volatility",
    "wide_spread",
    "weak_volume_growth",
    "rsi_out_of_range",
    "ema_not_aligned",
    "macd_negative",
    "low_quality_score",
    "score_below_threshold",
    "excluded_symbol",
)

REJECTION_REASON_TO_FILTER_KEY = {
    "low_quote_volume": "min_quote_volume",
    "low_liquidity": "min_quote_volume",
    "low_trade_count": "min_trade_count",
    "low_volatility": "min_volatility",
    "wide_spread": "max_spread_percent",
    "spread_unavailable": "max_spread_percent",
    "volume_growth_unavailable": "volume_growth_multiplier",
    "weak_volume_growth": "volume_growth_multiplier",
    "rsi_out_of_range": "rsi_min_15m",
    "ema_not_aligned": "ema_rule",
    "macd_negative": "macd_rule",
    "low_quality_score": "quality_score_min",
    "score_below_threshold": "lightweight_score_min",
    "excluded_symbol": "excluded_symbols",
}

FILTER_COUNT_KEYS = (
    "scan_limit",
    "scan_deep_analysis_limit",
    "min_quote_volume",
    "min_trade_count",
    "min_volatility",
    "max_spread_percent",
    "volume_growth_multiplier",
    "rsi_min_15m",
    "rsi_max_15m",
    "rsi_min_1h",
    "rsi_max_1h",
    "rsi_min_4h",
    "rsi_max_4h",
    "excluded_symbols",
    "stable_pair_guard",
    "leveraged_token_guard",
    "invalid_price_guard",
    "ema_rule",
    "macd_rule",
    "rsi_period",
    "quality_score_min",
    "lightweight_score_min",
)


def first_rejection_reason(reasons: list | tuple | None) -> str | None:
    clean = [str(reason) for reason in (reasons or []) if reason]
    if not clean:
        return None
    for reason in COINFILTER_REJECTION_ORDER:
        if reason in clean:
            return reason
    return clean[0]


def build_unique_filter_rejection_counts(scan_rows: list | None, universe_breakdown: dict | None = None) -> dict:
    counts = {key: 0 for key in FILTER_COUNT_KEYS}
    universe = universe_breakdown if isinstance(universe_breakdown, dict) else {}
    universe_key_map = {
        "stable_pair": "stable_pair_guard",
        "leveraged_token": "leveraged_token_guard",
        "invalid_price": "invalid_price_guard",
        **REJECTION_REASON_TO_FILTER_KEY,
    }
    for reason, value in universe.items():
        key = universe_key_map.get(str(reason))
        if key:
            counts[key] += _safe_int(value, 0)
    for row in scan_rows if isinstance(scan_rows, list) else []:
        if not isinstance(row, dict) or row.get("passed") is True:
            continue
        reason = row.get("first_rejection_reason") or first_rejection_reason(row.get("rejection_reasons")) or row.get("reason")
        key = REJECTION_REASON_TO_FILTER_KEY.get(str(reason or ""))
        if key:
            counts[key] += 1
    return counts


def build_filter_rejection_counts(universe_breakdown: dict | None, technical_breakdown: dict | None) -> dict:
    """Build cumulative diagnostic counts mapped to CoinFilter setting rows.

    The canonical unique counter is build_unique_filter_rejection_counts().
    This helper remains cumulative for compatibility and diagnostics.
    """
    merged = _merge_breakdowns(universe_breakdown, technical_breakdown)

    def count(*keys: str) -> int:
        return sum(_safe_int(merged.get(key), 0) for key in keys)

    return {
        "scan_limit": 0,
        "scan_deep_analysis_limit": 0,
        "min_quote_volume": count("low_quote_volume", "low_liquidity"),
        "min_trade_count": count("low_trade_count"),
        "min_volatility": count("low_volatility"),
        "max_spread_percent": count("wide_spread", "spread_unavailable"),
        "volatility_interval": count("low_volatility"),
        "volatility_candle_count": count("low_volatility"),
        "volume_growth_multiplier": count("weak_volume_growth", "volume_growth_unavailable"),
        "rsi_min_15m": count("rsi_out_of_range"),
        "rsi_max_15m": count("rsi_out_of_range"),
        "rsi_min_1h": count("rsi_out_of_range"),
        "rsi_max_1h": count("rsi_out_of_range"),
        "rsi_min_4h": count("rsi_out_of_range"),
        "rsi_max_4h": count("rsi_out_of_range"),
        "excluded_symbols": count("excluded_symbol"),
        "stable_pair_guard": count("stable_pair"),
        "leveraged_token_guard": count("leveraged_token"),
        "invalid_price_guard": count("invalid_price"),
        "ema_rule": count("ema_not_aligned"),
        "macd_rule": count("macd_negative"),
        "rsi_period": count("rsi_out_of_range"),
        "quality_score_min": count("low_quality_score"),
        "lightweight_score_min": count("score_below_threshold"),
    }


def _finite_float(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _numeric_series(rows: list, index: int) -> tuple[list[float], bool]:
    values: list[float] = []
    invalid = False
    for row in rows if isinstance(rows, list) else []:
        raw = row[index] if isinstance(row, (list, tuple)) and len(row) > index else None
        value = _finite_float(raw)
        if value is None:
            invalid = True
            continue
        values.append(value)
    return values, invalid


def _technical_numeric_reject(symbol: str, reason: str = "invalid_numeric_indicator") -> dict:
    return {
        "symbol": symbol,
        "price": 0.0,
        "volatility": 0.0,
        "volume_today": 0.0,
        "quote_volume": 0.0,
        "trade_count": 0,
        "spread_percent": 0.0,
        "quality_score": 0.0,
        "rsi": 0.0,
        "rsi_15m": 0.0,
        "rsi_1h": 0.0,
        "rsi_4h": 0.0,
        "volume_growth": False,
        "ema_signal": False,
        "macd_signal": False,
        "passed": False,
        "score": 0.0,
        "reason": reason,
        "rejection_reasons": [reason],
        "analysis_depth": "technical_rejected",
    }


def get_coin_filter_config(settings: dict) -> dict:
    coin_filter = settings.get("coin_filter", {}) if isinstance(settings, dict) else {}
    risk = settings.get("risk", {}) if isinstance(settings, dict) else {}

    excluded_raw = coin_filter.get(
        "excluded_symbols",
        DEFAULT_COIN_FILTER["excluded_symbols"]
    )

    excluded_symbols = {
        item.strip().upper()
        for item in str(excluded_raw).split(",")
        if item.strip()
    }

    return {
        "excluded_symbols": excluded_symbols,
        "min_volatility": _safe_float(coin_filter.get("min_volatility", 0.4), 0.4),
        "volatility_candle_count": _safe_int(coin_filter.get("volatility_candle_count", 12), 12),
        "volatility_interval": str(coin_filter.get("volatility_interval", "15m")),
        "rsi_min_15m": _safe_float(coin_filter.get("rsi_min_15m", 50), 50),
        "rsi_max_15m": _safe_float(coin_filter.get("rsi_max_15m", 75), 75),
        "rsi_min_1h": _safe_float(coin_filter.get("rsi_min_1h", 50), 50),
        "rsi_max_1h": _safe_float(coin_filter.get("rsi_max_1h", 75), 75),
        "rsi_min_4h": _safe_float(coin_filter.get("rsi_min_4h", 50), 50),
        "rsi_max_4h": _safe_float(coin_filter.get("rsi_max_4h", 75), 75),
        "volume_growth_multiplier": _safe_float(coin_filter.get("volume_growth_multiplier", 1.0), 1.0),
        "min_quote_volume": _safe_float(coin_filter.get("min_quote_volume", 1_000_000), 1_000_000),
        "min_quote_volume_raw": coin_filter.get("min_quote_volume", 1_000_000),
        "min_trade_count": _safe_int(coin_filter.get("min_trade_count", 1000), 1000),
        "max_spread_percent": _safe_float(risk.get("max_spread_percent", 0.35), 0.35),
        "quality_score_min": _safe_float(coin_filter.get("quality_score_min", 45), 45),
        "lightweight_score_min": _safe_float(coin_filter.get("lightweight_score_min", coin_filter.get("score_min", 55)), 55),
    }


def build_scan_settings_snapshot(settings: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or get_coin_filter_config(settings)
    coin_filter = settings.get("coin_filter", {}) if isinstance(settings, dict) else {}
    bot_settings = settings.get("bot", {}) if isinstance(settings, dict) else {}
    return {
        "coin_filter": {
            "min_quote_volume": coin_filter.get("min_quote_volume", cfg.get("min_quote_volume")),
            "min_trade_count": coin_filter.get("min_trade_count", cfg.get("min_trade_count")),
            "min_volatility": coin_filter.get("min_volatility", cfg.get("min_volatility")),
            "volatility_interval": coin_filter.get("volatility_interval", cfg.get("volatility_interval")),
            "volatility_candle_count": coin_filter.get("volatility_candle_count", cfg.get("volatility_candle_count")),
            "volume_growth_multiplier": coin_filter.get("volume_growth_multiplier", cfg.get("volume_growth_multiplier")),
            "rsi_min_15m": coin_filter.get("rsi_min_15m", cfg.get("rsi_min_15m")),
            "rsi_max_15m": coin_filter.get("rsi_max_15m", cfg.get("rsi_max_15m")),
            "rsi_min_1h": coin_filter.get("rsi_min_1h", cfg.get("rsi_min_1h")),
            "rsi_max_1h": coin_filter.get("rsi_max_1h", cfg.get("rsi_max_1h")),
            "rsi_min_4h": coin_filter.get("rsi_min_4h", cfg.get("rsi_min_4h")),
            "rsi_max_4h": coin_filter.get("rsi_max_4h", cfg.get("rsi_max_4h")),
            "lightweight_score_min": coin_filter.get("lightweight_score_min", coin_filter.get("score_min", cfg.get("lightweight_score_min"))),
            "quality_score_min": coin_filter.get("quality_score_min", cfg.get("quality_score_min")),
            "excluded_symbols": coin_filter.get("excluded_symbols"),
            "max_spread_percent": (settings.get("risk") or {}).get("max_spread_percent", cfg.get("max_spread_percent")),
        },
        "coin_filter_effective": {
            "min_quote_volume": cfg.get("min_quote_volume"),
            "min_quote_volume_raw": cfg.get("min_quote_volume_raw"),
            "volume_check_basis": "quoteVolume_USDT_24h",
            "min_trade_count": cfg.get("min_trade_count"),
            "min_volatility": cfg.get("min_volatility"),
            "volatility_interval": cfg.get("volatility_interval"),
            "volatility_candle_count": cfg.get("volatility_candle_count"),
            "volume_growth_multiplier": cfg.get("volume_growth_multiplier"),
            "rsi_min_15m": cfg.get("rsi_min_15m"),
            "rsi_max_15m": cfg.get("rsi_max_15m"),
            "rsi_min_1h": cfg.get("rsi_min_1h"),
            "rsi_max_1h": cfg.get("rsi_max_1h"),
            "rsi_min_4h": cfg.get("rsi_min_4h"),
            "rsi_max_4h": cfg.get("rsi_max_4h"),
            "lightweight_score_min": cfg.get("lightweight_score_min"),
            "quality_score_min": cfg.get("quality_score_min"),
            "max_spread_percent": cfg.get("max_spread_percent"),
            "excluded_symbols": sorted(cfg.get("excluded_symbols") or []),
        },
        "bot": {
            "scan_limit": bot_settings.get("scan_limit"),
            "scan_deep_analysis_limit": bot_settings.get("scan_deep_analysis_limit"),
        },
    }


def _build_rejection_reasons(row: dict, cfg: dict, quality: dict | None = None) -> list[str]:
    reasons = []
    if row.get("tradable") is False:
        reasons.extend(row.get("tradability_reasons") or ["not_tradable"])
    if _safe_float(row.get("price")) <= 0:
        reasons.append("invalid_price")
    if _safe_float(row.get("quote_volume")) < cfg["min_quote_volume"]:
        reasons.append("low_quote_volume")
    if _safe_int(row.get("trade_count")) < cfg["min_trade_count"]:
        reasons.append("low_trade_count")
    if _safe_float(row.get("volatility")) < cfg["min_volatility"]:
        reasons.append("low_volatility")
    spread = _finite_float(row.get("spread_percent"))
    if spread is None:
        reasons.append("spread_unavailable")
    elif spread > cfg["max_spread_percent"]:
        reasons.append("wide_spread")
    if quality:
        for reason in quality.get("reasons") or []:
            if reason not in reasons:
                reasons.append(reason)
        if _safe_float(quality.get("quality_score")) < cfg["quality_score_min"] and "low_quality_score" not in reasons:
            reasons.append("low_quality_score")
    if str(row.get("symbol") or "").upper() in cfg.get("excluded_symbols", set()):
        reasons.append("excluded_symbol")
    return reasons


def _lightweight_analyze_market_row(item: dict, settings: dict) -> dict:
    """Fast path used for the full Binance USDT universe.

    The previous implementation tried to download multi-timeframe klines for every
    symbol. That made 1000-symbol scans too slow and created the impression that
    only a few coins were scanned. This row-level analyzer evaluates every symbol
    from the 24h ticker first, then scan_market optionally deep-checks the best
    candidates.
    """
    cfg = get_coin_filter_config(settings)
    symbol = str(item.get("symbol") or "").upper()
    price = _safe_float(item.get("price") or item.get("lastPrice"))
    high = _safe_float(item.get("high_price") or item.get("highPrice"))
    low = _safe_float(item.get("low_price") or item.get("lowPrice"))
    quote_volume = _safe_float(item.get("quote_volume") or item.get("quoteVolume"))
    trade_count = _safe_int(item.get("trade_count") or item.get("count"))
    change_percent = _safe_float(item.get("change_percent") or item.get("priceChangePercent"))
    volatility = ((high - low) / price * 100) if price > 0 and high > 0 and low > 0 else 0.0
    spread_percent = _finite_float(item.get("spread_percent"))

    quality = score_coin_quality({
        **item,
        "price": price,
        "quote_volume": quote_volume,
        "volatility": volatility,
        "spread_percent": spread_percent,
    }, min_quote_volume=cfg["min_quote_volume"])

    volume_score = min(100, quote_volume / 5_000_000 * 100)
    trade_score = min(100, trade_count / 10_000 * 100)
    volatility_score = max(0, 100 - abs(volatility - 2.0) * 25)
    momentum_score = max(0, min(100, 50 + change_percent * 6))
    quality_score = _safe_float(quality.get("quality_score"))
    score = round(
        volume_score * 0.25 +
        trade_score * 0.10 +
        volatility_score * 0.20 +
        momentum_score * 0.15 +
        quality_score * 0.30,
        2,
    )

    reasons = _build_rejection_reasons({**item, "price": price, "quote_volume": quote_volume, "trade_count": trade_count, "volatility": volatility}, cfg, quality)
    score_threshold = _safe_float(cfg.get("lightweight_score_min"), 55)
    if score < score_threshold:
        _add_reason(reasons, "score_below_threshold")
    passed = not reasons
    return {
        "symbol": symbol,
        "price": price,
        "change_percent": round(change_percent, 4),
        "volatility": round(volatility, 4),
        "volatility_interval": "24h_proxy",
        "volatility_candle_count": 1,
        "volume_today": round(quote_volume, 2),
        "quote_volume": round(quote_volume, 2),
        "trade_count": trade_count,
        "recent_volume": round(quote_volume, 2),
        "previous_volume_avg": None,
        "volume_growth": None,
        "volume_growth_source": "not_evaluated_in_lightweight_prefilter",
        "ema_signal": None,
        "rsi": None,
        "rsi_15m": None,
        "rsi_1h": None,
        "rsi_4h": None,
        "rsi_signal": None,
        "macd_signal": None,
        "technical_data_source": "not_evaluated",
        "technical_evaluated": False,
        "prefilter_passed": passed,
        "quality_score": quality.get("quality_score"),
        "quality_bucket": quality.get("bucket"),
        "quality_reasons": quality.get("reasons", []),
        "quality_components": quality.get("components", {}),
        "spread_percent": round(spread_percent, 6) if spread_percent is not None else None,
        "spread_source": item.get("spread_source", "unavailable"),
        "passed": passed,
        "score": score,
        "reason": None if passed else (reasons[0] if reasons else "score_below_threshold"),
        "rejection_reasons": [] if passed else reasons,
        "analysis_depth": "lightweight_full_universe",
    }


def _cancelled(cancel_requested=None, deadline: float | None = None) -> bool:
    return bool(
        (callable(cancel_requested) and cancel_requested())
        or (deadline is not None and time.monotonic() >= deadline)
    )


def _remaining_timeout(deadline: float | None, cap: float = 10.0, cancel_requested=None) -> float:
    if _cancelled(cancel_requested, deadline):
        raise TimeoutError("scan_cancelled_or_deadline")
    if deadline is None:
        return cap
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("deep_analysis_timeout")
    return max(0.1, min(cap, remaining))


def _fetch_klines_with_timeout(symbol: str, interval: str, limit: int, deadline: float | None, cancel_requested=None):
    timeout = _remaining_timeout(deadline, cancel_requested=cancel_requested)
    try:
        return fetch_klines(symbol, interval, limit, timeout=timeout)
    except TypeError as error:
        if "timeout" not in str(error):
            raise
        return fetch_klines(symbol, interval, limit)


def _get_market_symbols_with_timeout(*, limit: int, settings: dict, strict: bool, deadline: float, cancel_requested=None):
    timeout = _remaining_timeout(deadline, cancel_requested=cancel_requested)
    try:
        return get_market_symbols(limit=limit, settings=settings, strict=strict, timeout=timeout)
    except TypeError as error:
        if "timeout" not in str(error):
            raise
        return get_market_symbols(limit=limit, settings=settings, strict=strict)


def calculate_volume_growth(volumes: list[float], multiplier: float, recent_window: int = 4, previous_window: int = 20) -> dict:
    required = recent_window + previous_window
    if len(volumes) < required:
        return {"available": False, "passed": False, "reason": "insufficient_kline_quote_volume", "recent_avg": None, "previous_avg": None}
    recent = volumes[-recent_window:]
    previous = volumes[-required:-recent_window]
    recent_avg = sum(recent) / len(recent)
    previous_avg = sum(previous) / len(previous)
    if previous_avg <= 0:
        return {"available": False, "passed": False, "reason": "non_positive_previous_quote_volume", "recent_avg": recent_avg, "previous_avg": previous_avg}
    return {
        "available": True,
        "passed": recent_avg > previous_avg * multiplier,
        "reason": None,
        "recent_avg": recent_avg,
        "previous_avg": previous_avg,
    }


def analyze_symbol(symbol: str, settings: dict, *, market_row: dict | None = None, deadline: float | None = None, cancel_requested=None) -> dict:
    symbol = symbol.upper()
    filter_config = get_coin_filter_config(settings)

    if symbol in filter_config["excluded_symbols"]:
        return {
            "symbol": symbol,
            "passed": False,
            "score": 0,
            "reason": "excluded_symbol",
            "rejection_reasons": ["excluded_symbol"],
            "analysis_depth": "technical",
        }

    volatility_interval = filter_config["volatility_interval"]
    volatility_candle_count = max(filter_config["volatility_candle_count"], 2)

    market_row = market_row if isinstance(market_row, dict) else {}
    kline_limit = max(volatility_candle_count, 80)
    klines_15m = _fetch_klines_with_timeout(symbol, "15m", kline_limit, deadline, cancel_requested)
    klines_1h = _fetch_klines_with_timeout(symbol, "1h", 80, deadline, cancel_requested)
    klines_4h = _fetch_klines_with_timeout(symbol, "4h", 80, deadline, cancel_requested)
    interval_rows = {"15m": klines_15m, "1h": klines_1h, "4h": klines_4h}
    klines_volatility = interval_rows.get(volatility_interval)
    if klines_volatility is None:
        klines_volatility = _fetch_klines_with_timeout(symbol, volatility_interval, max(volatility_candle_count, 20), deadline, cancel_requested)

    closes_15m, invalid_closes_15m = _numeric_series(klines_15m, 4)
    closes_1h, invalid_closes_1h = _numeric_series(klines_1h, 4)
    closes_4h, invalid_closes_4h = _numeric_series(klines_4h, 4)
    volumes_15m, invalid_volumes_15m = _numeric_series(klines_15m, 7)
    highs_volatility, invalid_highs = _numeric_series(klines_volatility, 2)
    lows_volatility, invalid_lows = _numeric_series(klines_volatility, 3)

    if any([
        invalid_closes_15m, invalid_closes_1h, invalid_closes_4h,
        invalid_volumes_15m, invalid_highs, invalid_lows,
    ]):
        return _technical_numeric_reject(symbol)
    if not closes_15m or not closes_1h or not closes_4h:
        return _technical_numeric_reject(symbol, "missing_numeric_indicator")

    price = closes_15m[-1] if closes_15m else 0
    selected_highs = highs_volatility[-volatility_candle_count:]
    selected_lows = lows_volatility[-volatility_candle_count:]
    volatility = ((max(selected_highs) - min(selected_lows)) / price) * 100 if price and selected_highs and selected_lows else 0
    volume_today = _safe_float(market_row.get("quote_volume"))
    volume_growth_result = calculate_volume_growth(volumes_15m, filter_config["volume_growth_multiplier"])
    recent_volume = volume_growth_result.get("recent_avg")
    previous_volume_avg = volume_growth_result.get("previous_avg")
    volume_growth = bool(volume_growth_result.get("passed"))

    ema_15m_fast = _finite_float(ema(closes_15m[-30:], 9))
    ema_15m_slow = _finite_float(ema(closes_15m[-60:], 21))
    ema_1h_fast = _finite_float(ema(closes_1h[-30:], 9))
    ema_1h_slow = _finite_float(ema(closes_1h[-60:], 21))
    if None in {ema_15m_fast, ema_15m_slow, ema_1h_fast, ema_1h_slow}:
        return _technical_numeric_reject(symbol)
    ema_signal = ema_15m_fast > ema_15m_slow and ema_1h_fast > ema_1h_slow

    rsi_15m = _finite_float(rsi(closes_15m, 14))
    rsi_1h = _finite_float(rsi(closes_1h, 14))
    rsi_4h = _finite_float(rsi(closes_4h, 14))
    if None in {rsi_15m, rsi_1h, rsi_4h}:
        return _technical_numeric_reject(symbol)
    rsi_signal = (
        filter_config["rsi_min_15m"] <= rsi_15m <= filter_config["rsi_max_15m"] and
        filter_config["rsi_min_1h"] <= rsi_1h <= filter_config["rsi_max_1h"] and
        filter_config["rsi_min_4h"] <= rsi_4h <= filter_config["rsi_max_4h"]
    )

    macd_result = calculate_macd(closes_15m)
    if not isinstance(macd_result, dict):
        return _technical_numeric_reject(symbol)
    macd_value = _finite_float(macd_result.get("value"))
    macd_signal_value = _finite_float(macd_result.get("signal"))
    macd_histogram = _finite_float(macd_result.get("histogram"))
    if None in {macd_value, macd_signal_value, macd_histogram}:
        return _technical_numeric_reject(symbol)
    macd_signal = macd_value > macd_signal_value and macd_histogram > 0

    spread_percent = _finite_float(market_row.get("spread_percent"))
    spread_available = spread_percent is not None
    quality = score_coin_quality({
        "symbol": symbol,
        "price": price,
        "quote_volume": volume_today,
        "volatility": volatility,
        "spread_percent": spread_percent,
    }, min_quote_volume=filter_config["min_quote_volume"])

    passed = (
        volatility >= filter_config["min_volatility"] and
        volume_today >= filter_config["min_quote_volume"] and
        spread_available and
        spread_percent <= filter_config["max_spread_percent"] and
        volume_growth_result.get("available") is True and
        volume_growth and
        ema_signal and
        rsi_signal and
        macd_signal and
        _safe_float(quality.get("quality_score")) >= filter_config["quality_score_min"]
    )

    score = (
        (volatility * 2) +
        (_safe_float(recent_volume) / 1_000_000) +
        (volume_today / 10_000_000) +
        (rsi_15m / 10) +
        (10 if macd_signal else 0) +
        (_safe_float(quality.get("quality_score")) / 5)
    )

    rejection_reasons = []
    if price <= 0:
        rejection_reasons.append("invalid_price")
    if volume_today < filter_config["min_quote_volume"]:
        rejection_reasons.append("low_quote_volume")
    if volatility < filter_config["min_volatility"]:
        rejection_reasons.append("low_volatility")
    if not spread_available:
        rejection_reasons.append("spread_unavailable")
    elif spread_percent > filter_config["max_spread_percent"]:
        rejection_reasons.append("wide_spread")
    if volume_growth_result.get("available") is not True:
        rejection_reasons.append("volume_growth_unavailable")
    elif not volume_growth:
        rejection_reasons.append("weak_volume_growth")
    if not ema_signal:
        rejection_reasons.append("ema_not_aligned")
    if not rsi_signal:
        rejection_reasons.append("rsi_out_of_range")
    if not macd_signal:
        rejection_reasons.append("macd_negative")
    if _safe_float(quality.get("quality_score")) < filter_config["quality_score_min"]:
        rejection_reasons.append("low_quality_score")

    return {
        "symbol": symbol,
        "price": price,
        "volatility": round(volatility, 2),
        "volatility_interval": volatility_interval,
        "volatility_candle_count": volatility_candle_count,
        "volume_today": round(volume_today, 2),
        "quote_volume": round(volume_today, 2),
        "recent_volume": round(recent_volume, 2) if recent_volume is not None else None,
        "previous_volume_avg": round(previous_volume_avg, 2) if previous_volume_avg is not None else None,
        "volume_growth": volume_growth,
        "volume_growth_available": volume_growth_result.get("available") is True,
        "volume_growth_source": "binance_15m_kline_quote_volume",
        "volume_growth_unavailable_reason": volume_growth_result.get("reason"),
        "ema_signal": ema_signal,
        "rsi": round(rsi_15m, 2),
        "rsi_15m": round(rsi_15m, 2),
        "rsi_1h": round(rsi_1h, 2),
        "rsi_4h": round(rsi_4h, 2),
        "rsi_signal": rsi_signal,
        "macd_signal": macd_signal,
        "macd": round(macd_value, 8),
        "macd_signal_value": round(macd_signal_value, 8),
        "macd_histogram": round(macd_histogram, 8),
        "quality_score": quality.get("quality_score"),
        "quality_bucket": quality.get("bucket"),
        "quality_reasons": quality.get("reasons", []),
        "quality_components": quality.get("components", {}),
        "spread_percent": round(spread_percent, 6) if spread_percent is not None else None,
        "spread_source": market_row.get("spread_source", "unavailable"),
        "technical_data_source": "binance_klines",
        "technical_evaluated": True,
        "passed": passed,
        "score": round(score, 2),
        "reason": None if passed else (rejection_reasons[0] if rejection_reasons else "not_passed"),
        "rejection_reasons": [] if passed else rejection_reasons,
        "analysis_depth": "technical",
    }


def _scan_row_from_analysis(analysis: dict) -> dict:
    status = "PASSED" if analysis.get("passed") else ("REJECT" if analysis.get("rejection_reasons") else "WATCH")
    return {
        "symbol": analysis.get("symbol"),
        "price": _safe_float(analysis.get("price")),
        "score": _safe_float(analysis.get("score")),
        "status": status,
        "passed": bool(analysis.get("passed")),
        "reason": analysis.get("reason"),
        "first_rejection_reason": analysis.get("first_rejection_reason") or first_rejection_reason(analysis.get("rejection_reasons")),
        "rejection_reasons": analysis.get("rejection_reasons", []),
        "volatility": _safe_float(analysis.get("volatility")),
        "rsi": _safe_float(analysis.get("rsi")),
        "rsi_15m": _safe_float(analysis.get("rsi_15m", analysis.get("rsi"))),
        "rsi_1h": _safe_float(analysis.get("rsi_1h")),
        "rsi_4h": _safe_float(analysis.get("rsi_4h")),
        "volume_growth": analysis.get("volume_growth"),
        "ema_signal": analysis.get("ema_signal"),
        "macd_signal": analysis.get("macd_signal"),
        "volume_today": _safe_float(analysis.get("volume_today")),
        "quote_volume": _safe_float(analysis.get("quote_volume", analysis.get("volume_today"))),
        "trade_count": _safe_int(analysis.get("trade_count")),
        "spread_percent": _safe_float(analysis.get("spread_percent")),
        "quality_score": _safe_float(analysis.get("quality_score")),
        "quality_bucket": analysis.get("quality_bucket"),
        "analysis_depth": analysis.get("analysis_depth"),
        "technical_evaluated": analysis.get("technical_evaluated"),
        "technical_data_source": analysis.get("technical_data_source"),
        "volume_growth_source": analysis.get("volume_growth_source"),
        "spread_source": analysis.get("spread_source"),
    }


def build_coinfilter_pipeline(scan: dict, *, test_scan: bool = False) -> dict:
    total_seen = _safe_int(scan.get("universe_total_seen"), _safe_int(scan.get("scanned"), 0))
    universe_rejected = _safe_int(scan.get("universe_rejected_count"), 0)
    eligible = _safe_int(scan.get("eligible_universe_count"), max(total_seen - universe_rejected, 0))
    candidates_count = _safe_int(scan.get("candidates_count"), 0)
    rejected_count = _safe_int(scan.get("rejected_count"), max(eligible - candidates_count, 0))
    disabled = {"status": "not_run_in_coinfilter_test"} if test_scan else {"status": "not_evaluated_in_scan_market"}

    return {
        "market_universe": {
            "total_seen": total_seen,
            "passed": eligible,
            "rejected": universe_rejected,
            "top_rejection_reason": None,
        },
        "coinfilter": {
            "passed": candidates_count,
            "rejected": rejected_count,
            "top_rejection_reason": scan.get("top_rejection_reason"),
        },
        "strategy": dict(disabled),
        "karabasan": dict(disabled),
        "risk": dict(disabled),
        "execution": dict(disabled),
    }


def build_candidate_handoff(scan: dict) -> dict:
    candidates = [
        dict(candidate)
        for candidate in (scan.get("candidates") or [])
        if isinstance(candidate, dict) and candidate.get("passed") is True
    ]
    rows = [dict(row) for row in (scan.get("scan_rows") or []) if isinstance(row, dict)]
    return {
        "contract": "coinfilter_candidate_handoff_v1",
        "scan_id": scan.get("scan_id"),
        "time": scan.get("time"),
        "settings_used": scan.get("settings_used") or scan.get("coin_filter_settings_used") or {},
        "passed": len(candidates),
        "candidates": candidates,
        "scan_rows": rows,
    }


def scan_market(settings: dict, limit: int = 1000, *, deep_analysis: bool = True, timeout_seconds: float = 20, deep_analysis_timeout_seconds: float = 15, cancel_requested=None, deadline: float | None = None) -> dict:
    scan_started_monotonic = time.monotonic()
    scan_deadline = scan_started_monotonic + max(1.0, min(float(timeout_seconds or 20), 20.0))
    if deadline is not None:
        scan_deadline = min(scan_deadline, deadline)
    deep_deadline = min(scan_deadline, scan_started_monotonic + max(1.0, min(float(deep_analysis_timeout_seconds or 15), 15.0)))
    scan_started_at = datetime.now().isoformat(timespec="seconds")
    limit = max(1, min(_safe_int(limit, 1000), 1500))
    market = _get_market_symbols_with_timeout(limit=limit, settings=settings, strict=True, deadline=scan_deadline, cancel_requested=cancel_requested)
    now_text = datetime.now().isoformat(timespec="seconds")
    scan_id = str(uuid4())

    if market.get("status") != "ok" or not market.get("live"):
        error_payload = {
            "status": "error", "mode": "shadow", "live": False, "source": "binance", "time": now_text,
            "scan_id": scan_id, "scanned": 0, "eligible_universe_count": 0, "universe_total_seen": 0,
            "universe_rejected_count": 0, "universe_rejection_breakdown": {}, "candidates_count": 0,
            "rejected_count": 0, "top_rejection_reason": None, "rejection_breakdown": {}, "candidates": [],
            "passed": 0, "settings_used": {},
            "scan_rows": [], "scan_diagnostics": {
                "mode": "error",
                "deep_analysis_enabled": bool(deep_analysis),
                "deep_analysis_limit": 0,
                "deep_analyzed_count": 0,
            },
            "scan_trace": {"scan_id": scan_id, "start_time": scan_started_at, "end_time": datetime.now().isoformat(timespec="seconds"), "duration_ms": round((time.monotonic() - scan_started_monotonic) * 1000, 2), "status": "error", "error_count": 1},
            "error": market.get("error", "market data failed")
        }
        error_payload["pipeline"] = build_coinfilter_pipeline(error_payload)
        error_payload["candidate_handoff"] = build_candidate_handoff(error_payload)
        return error_payload

    cfg = get_coin_filter_config(settings)
    settings_snapshot = build_scan_settings_snapshot(settings, cfg)
    coin_filter_settings_used = settings_snapshot.get("coin_filter_effective", {})
    risk_settings = settings.get("risk", {}) if isinstance(settings, dict) else {}
    take_profit_raw = str(risk_settings.get("take_profit", "2%")).replace("%", "")
    try:
        take_profit = float(take_profit_raw) / 100
    except ValueError:
        take_profit = 0.02

    market_symbols = market.get("symbols", []) or []
    lightweight_results = []
    for item in market_symbols:
        if _cancelled(cancel_requested, scan_deadline):
            raise TimeoutError("scan_cancelled_or_deadline")
        try:
            lightweight_results.append(_lightweight_analyze_market_row(item, settings))
        except Exception as error:
            symbol = str(item.get("symbol") or "-").upper()
            lightweight_results.append({
                "symbol": symbol,
                "passed": False,
                "score": 0,
                "reason": "analysis_error",
                "rejection_reasons": ["analysis_error"],
                "error": str(error),
                "analysis_depth": "failed_lightweight",
            })

    deep_limit = 0
    deep_symbols: set[str] = set()
    results = lightweight_results

    if deep_analysis:
        # Technical analysis is reserved for normal bot scans. CoinFilter test
        # scans stay on the single Binance 24h ticker request.
        bot_settings = settings.get("bot", {}) if isinstance(settings, dict) else {}
        deep_limit = max(0, min(_safe_int(bot_settings.get("scan_deep_analysis_limit"), 8), 8))
        ranked_for_deep = sorted(
            (row for row in lightweight_results if row.get("prefilter_passed") is True),
            key=lambda row: (_safe_float(row.get("score")), _safe_float(row.get("quote_volume"))),
            reverse=True,
        )
        deep_symbols = {row.get("symbol") for row in ranked_for_deep[:deep_limit] if row.get("symbol")}

        results = []
        for row in lightweight_results:
            if _cancelled(cancel_requested, scan_deadline):
                raise TimeoutError("scan_cancelled_or_deadline")
            symbol = row.get("symbol")
            if symbol in deep_symbols:
                try:
                    technical = analyze_symbol(symbol, settings, market_row=row, deadline=deep_deadline, cancel_requested=cancel_requested)
                    # Preserve Binance universe fields from lightweight pass.
                    technical["quote_volume"] = row.get("quote_volume") or technical.get("volume_today")
                    technical["trade_count"] = row.get("trade_count")
                    technical["quality_score"] = max(_safe_float(technical.get("quality_score")), _safe_float(row.get("quality_score")))
                    technical["quality_bucket"] = technical.get("quality_bucket") or row.get("quality_bucket")
                    if technical.get("spread_percent") is None:
                        technical["spread_percent"] = row.get("spread_percent")
                    results.append(technical)
                except TimeoutError:
                    raise
                except Exception as error:
                    row["passed"] = False
                    row["reason"] = "technical_analysis_error"
                    row["rejection_reasons"] = list(set((row.get("rejection_reasons") or []) + ["technical_analysis_error"]))
                    row["error"] = str(error)
                    results.append(row)
            else:
                if row.get("prefilter_passed") is True:
                    row["passed"] = False
                    row["reason"] = "deep_analysis_limit_not_selected"
                    row["rejection_reasons"] = ["deep_analysis_limit_not_selected"]
                results.append(row)

    rejection_counter = Counter()
    candidates = []
    scan_rows = []
    for analysis in results:
        if _cancelled(cancel_requested, scan_deadline):
            raise TimeoutError("scan_cancelled_or_deadline")
        price = _safe_float(analysis.get("price"))
        sell_target = round(price * (1 + take_profit), 8) if price > 0 else 0
        row = _scan_row_from_analysis(analysis)
        row["sell_target"] = sell_target
        scan_rows.append(row)

        if analysis.get("passed"):
            candidates.append({**analysis, "sell_target": sell_target})
        else:
            reasons = analysis.get("rejection_reasons") or [analysis.get("reason") or "not_passed"]
            first_reason = first_rejection_reason(reasons) or "not_passed"
            analysis["first_rejection_reason"] = first_reason
            analysis["reason"] = first_reason
            row["first_rejection_reason"] = first_reason
            row["reason"] = first_reason
            for reason in reasons:
                rejection_counter[reason] += 1

    candidates.sort(key=lambda item: (_safe_float(item.get("score")), _safe_float(item.get("quality_score")), _safe_float(item.get("quote_volume"))), reverse=True)
    scan_rows.sort(key=lambda item: (_safe_float(item.get("score")), _safe_float(item.get("quote_volume"))), reverse=True)
    top_reason = rejection_counter.most_common(1)[0][0] if rejection_counter else None
    unique_universe_breakdown = market.get("universe_rejection_breakdown_unique", {})
    unique_filter_counts = build_unique_filter_rejection_counts(scan_rows, unique_universe_breakdown)
    cumulative_filter_counts = build_filter_rejection_counts(market.get("universe_rejection_breakdown", {}), dict(rejection_counter))
    unique_reason_counter = Counter(
        row.get("first_rejection_reason")
        for row in scan_rows
        if row.get("passed") is not True and row.get("first_rejection_reason")
    )
    top_reason = unique_reason_counter.most_common(1)[0][0] if unique_reason_counter else top_reason

    vol_values = [_safe_float(row.get("volatility")) for row in scan_rows if _safe_float(row.get("volatility")) > 0]
    quality_values = [_safe_float(row.get("quality_score")) for row in scan_rows if _safe_float(row.get("quality_score")) > 0]

    payload = {
        "status": "ok",
        "mode": "shadow",
        "live": True,
        "source": "binance",
        "time": now_text,
        "scan_id": scan_id,
        "scanned": len(results),
        "eligible_universe_count": market.get("count", len(results)),
        "universe_total_seen": market.get("total_seen", len(results)),
        "universe_rejected_count": market.get("universe_rejected_count", 0),
        "universe_rejection_breakdown": market.get("universe_rejection_breakdown", {}),
        "universe_rejection_breakdown_unique": unique_universe_breakdown,
        "candidates_count": len(candidates),
        "passed": len(candidates),
        "rejected_count": len(results) - len(candidates),
        "top_rejection_reason": top_reason,
        "rejection_breakdown": dict(rejection_counter),
        "filter_rejection_counts": unique_filter_counts,
        "filter_rejection_counts_cumulative": cumulative_filter_counts,
        "settings_snapshot": settings_snapshot,
        "coin_filter_settings_used": coin_filter_settings_used,
        "settings_used": coin_filter_settings_used,
        "settings_changed_since_scan": False,
        "candidates": candidates[:100],
        "scan_rows": scan_rows,
        "scan_diagnostics": {
            "mode": "full_universe_plus_deep_technical" if deep_analysis else "coinfilter_lightweight_test_scan",
            "requested_limit": limit,
            "deep_analysis_enabled": bool(deep_analysis),
            "deep_analysis_limit": deep_limit,
            "deep_analyzed_count": len(deep_symbols),
            "coin_filter_settings_used": {**coin_filter_settings_used, "scan_deep_analysis_limit": _safe_int((settings.get("bot") or {}).get("scan_deep_analysis_limit"), 80)},
            "filter_rejection_counts": unique_filter_counts,
            "filter_rejection_counts_cumulative": cumulative_filter_counts,
            "volume_rejection_diagnostics": market.get("volume_rejection_diagnostics", {}),
            "avg_volatility": round(mean(vol_values), 4) if vol_values else 0,
            "avg_quality_score": round(mean(quality_values), 2) if quality_values else 0,
            "coverage_note": "scanned tüm uygun USDT spot evrenini sayar; deep_analysis_limit en iyi adaylarda teknik doğrulama yapar.",
        },
        "scan_trace": {
            "scan_id": scan_id,
            "start_time": scan_started_at,
            "end_time": datetime.now().isoformat(timespec="seconds"),
            "duration_ms": round((time.monotonic() - scan_started_monotonic) * 1000, 2),
            "total_pairs": market.get("total_seen", len(results)),
            "eligible_universe": market.get("count", len(results)),
            "deep_analyzed_count": len(deep_symbols),
            "candidate_count": len(candidates),
            "reject_count": len(results) - len(candidates),
            "error_count": 0,
            "binance_latency_ms": market.get("latency_ms"),
            "rate_limit_warning": market.get("rate_limit_warning"),
            "filter_version": (settings.get("coin_filter") or {}).get("version"),
            "strategy_version": (settings.get("current_strategy") or "default"),
            "runtime_health": "ok",
        },
        "error": None,
    }
    payload["pipeline"] = build_coinfilter_pipeline(payload)
    payload["candidate_handoff"] = build_candidate_handoff(payload)
    return payload


def scan_debug(settings: dict, limit: int = 10) -> dict:
    market = get_market_symbols(limit=limit, settings=settings, strict=True)
    return {
        "status": market.get("status"),
        "live": market.get("live"),
        "source": market.get("source"),
        "strict": market.get("strict"),
        "requested_limit": limit,
        "count": market.get("count", 0),
        "total_seen": market.get("total_seen", 0),
        "universe_rejected_count": market.get("universe_rejected_count", 0),
        "universe_rejection_breakdown": market.get("universe_rejection_breakdown", {}),
        "symbols_sample": market.get("symbols", [])[:limit],
        "diagnostic": "Market evreni Binance 24h ticker ile kurulur; bot scan detayları /api/bot/scan çıktısındaki scan_diagnostics alanındadır.",
        "error": market.get("error"),
    }
