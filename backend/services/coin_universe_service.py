import math


STABLE_BASES = {
    "USDC", "FDUSD", "BUSD", "TUSD", "DAI", "USDP", "USDS", "EUR", "TRY",
    "AEUR", "EURI", "PAX", "UST", "USTC", "SUSD", "GUSD", "PYUSD",
}

LEVERAGED_MARKERS = (
    "UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT",
)

LEVERAGED_PARTS = ("3L", "3S", "5L", "5S", "BULL", "BEAR")


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
        return int(value)
    except (TypeError, ValueError):
        return fallback


def base_asset(symbol: str) -> str:
    symbol = str(symbol or "").upper()
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def is_stable_pair(symbol: str) -> bool:
    return base_asset(symbol) in STABLE_BASES


def is_leveraged_token(symbol: str) -> bool:
    symbol = str(symbol or "").upper()
    base = base_asset(symbol)

    if symbol.endswith(LEVERAGED_MARKERS) and len(base) > 3:
        return True

    return any(base.endswith(part) for part in LEVERAGED_PARTS)


def tradability_guard(item: dict, settings: dict | None = None, strict: bool = True) -> dict:
    settings = settings or {}
    coin_filter = settings.get("coin_filter", {}) if isinstance(settings, dict) else {}

    symbol = str(item.get("symbol") or "").upper()
    quote_volume = _safe_float(item.get("quote_volume") or item.get("quoteVolume"))
    trade_count = _safe_int(item.get("trade_count") or item.get("count"))
    last_price = _safe_float(item.get("price") or item.get("lastPrice"))

    min_quote_volume_raw = coin_filter.get("min_quote_volume", 1_000_000)
    min_quote_volume = _safe_float(min_quote_volume_raw, 1_000_000)
    min_trade_count = _safe_int(coin_filter.get("min_trade_count", 1000), 1000)

    if not strict:
        min_quote_volume = 0
        min_trade_count = 0

    reasons = []

    if not symbol.endswith("USDT"):
        reasons.append("not_usdt_pair")
    if is_stable_pair(symbol):
        reasons.append("stable_pair")
    if is_leveraged_token(symbol):
        reasons.append("leveraged_token")
    if last_price <= 0:
        reasons.append("invalid_price")
    if quote_volume < min_quote_volume:
        reasons.append("low_quote_volume")
    if trade_count < min_trade_count:
        reasons.append("low_trade_count")

    return {
        "symbol": symbol,
        "tradable": len(reasons) == 0,
        "tradability_reasons": reasons,
        "quote_volume": quote_volume,
        "trade_count": trade_count,
        "price": last_price,
        "min_quote_volume": min_quote_volume,
        "min_quote_volume_raw": min_quote_volume_raw,
        "volume_check_basis": "quoteVolume_USDT_24h",
        "min_trade_count": min_trade_count,
    }


def build_coin_universe(items: list[dict], settings: dict | None = None, limit: int | None = None, strict: bool = True) -> dict:
    rows = []
    passed = []
    rejected = []
    breakdown = {}
    unique_breakdown = {}

    for item in items or []:
        guard = tradability_guard(item, settings, strict=strict)
        merged = {**item, **guard}
        rows.append(merged)

        if guard["tradable"]:
            passed.append(merged)
        else:
            rejected.append(merged)
            reasons = guard["tradability_reasons"] or ["not_tradable"]
            first_reason = reasons[0]
            merged["first_rejection_reason"] = first_reason
            unique_breakdown[first_reason] = unique_breakdown.get(first_reason, 0) + 1
            for reason in reasons:
                breakdown[reason] = breakdown.get(reason, 0) + 1

    passed.sort(key=lambda row: _safe_float(row.get("quote_volume")), reverse=True)
    selected = passed[:limit] if limit else passed

    low_quote_rows = [row for row in rejected if "low_quote_volume" in (row.get("tradability_reasons") or [])]
    min_quote_values = [row.get("min_quote_volume") for row in rows if row.get("min_quote_volume") is not None]
    effective_min_quote_volume = min_quote_values[0] if min_quote_values else 0

    return {
        "status": "ok",
        "count": len(selected),
        "total_seen": len(rows),
        "rejected_count": len(rejected),
        "rejection_breakdown": breakdown,
        "unique_rejection_breakdown": unique_breakdown,
        "symbols": selected,
        "rows": rows,
        "volume_rejection_diagnostics": {
            "basis": "quoteVolume_USDT_24h",
            "effective_min_quote_volume": effective_min_quote_volume,
            "low_quote_volume_count": len(low_quote_rows),
            "sample_low_quote_volume": [
                {
                    "symbol": row.get("symbol"),
                    "quote_volume": row.get("quote_volume"),
                    "quoteVolume_USDT_24h": row.get("quote_volume"),
                    "min_quote_volume": row.get("min_quote_volume"),
                }
                for row in low_quote_rows[:12]
            ],
        },
    }
