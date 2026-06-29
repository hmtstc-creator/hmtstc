from __future__ import annotations


def _safe_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def score_coin_quality(row: dict, min_quote_volume: float | int | str | None = None) -> dict:
    symbol = str(row.get("symbol") or "").upper()
    quote_volume = _safe_float(row.get("quote_volume") or row.get("volume_today"))
    spread_percent = _safe_float(row.get("spread_percent") or row.get("spread"), 0.08)
    volatility = _safe_float(row.get("volatility"))
    age_days = _safe_float(row.get("age_days"), 999)
    leveraged = any(token in symbol for token in ["UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT", "3LUSDT", "3SUSDT"])
    stable_like = symbol in {"USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT", "DAIUSDT", "EURUSDT"}
    configured_min_quote_volume = _safe_float(min_quote_volume, 2_000_000)
    if configured_min_quote_volume < 0:
        configured_min_quote_volume = 0

    liquidity_score = max(0, min(100, quote_volume / 5_000_000 * 100))
    spread_score = max(0, min(100, 100 - spread_percent * 220))
    volatility_score = max(0, min(100, 100 - abs(volatility - 2.0) * 25))
    age_score = 30 if age_days < 14 else 100
    penalty = 45 if leveraged else 0
    penalty += 30 if stable_like else 0
    quality = max(0, min(100, liquidity_score * 0.35 + spread_score * 0.25 + volatility_score * 0.25 + age_score * 0.15 - penalty))
    reasons = []
    if stable_like: reasons.append("stable_pair")
    if leveraged: reasons.append("leveraged_token")
    if quote_volume < configured_min_quote_volume: reasons.append("low_liquidity")
    if spread_percent > 0.35: reasons.append("wide_spread")
    if age_days < 14: reasons.append("new_listing_risk")
    return {
        "symbol": symbol,
        "quality_score": round(quality, 2),
        "bucket": "clean_spot" if quality >= 70 and not reasons else ("watch" if quality >= 45 else "reject"),
        "reasons": reasons,
        "components": {
            "liquidity": round(liquidity_score, 2),
            "configured_min_quote_volume": configured_min_quote_volume,
            "spread": round(spread_score, 2),
            "volatility": round(volatility_score, 2),
            "age": round(age_score, 2),
        },
    }


def enrich_coin_rows(rows: list[dict]) -> list[dict]:
    enriched = []
    for row in rows or []:
        item = dict(row)
        item["quality"] = score_coin_quality(item)
        enriched.append(item)
    return enriched
