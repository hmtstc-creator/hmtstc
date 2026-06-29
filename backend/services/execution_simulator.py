from __future__ import annotations

from math import isfinite
from uuid import uuid4

from core.storage import now_iso


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        number = float(value)
        return number if isfinite(number) else fallback
    except (TypeError, ValueError):
        return fallback


def _risk_value(settings: dict, key: str, fallback: float) -> float:
    risk = settings.get("risk", {}) if isinstance(settings, dict) else {}
    return _safe_float(risk.get(key), fallback)


def normalize_execution_settings(settings: dict) -> dict:
    return {
        "commission_percent": _risk_value(settings, "commission_percent", 0.10),
        "slippage_percent": _risk_value(settings, "slippage_percent", 0.05),
        "max_spread_percent": _risk_value(settings, "max_spread_percent", 0.35),
        "max_slippage_percent": _risk_value(settings, "max_slippage_percent", 0.35),
        "min_quote_volume": _risk_value(settings, "min_execution_quote_volume", 2_000_000),
        "liquidity_reject_enabled": True,
    }


def build_execution_quality(candidate: dict, settings: dict) -> dict:
    cfg = normalize_execution_settings(settings)
    price = _safe_float(candidate.get("price") or candidate.get("close"))
    quote_volume = _safe_float(candidate.get("quote_volume") or candidate.get("volume_today"))
    quality_score = _safe_float(candidate.get("quality_score"), 50.0)
    spread_percent = _safe_float(candidate.get("spread_percent") or candidate.get("spread"), 0.08)
    volatility = _safe_float(candidate.get("volatility"))

    # Revizyon_11: execution maliyeti statik değil; coin kalitesi, volatilite ve likiditeyle birlikte puanlanır.
    liquidity_pressure = 0.0 if quote_volume >= cfg["min_quote_volume"] * 2 else 0.04
    quality_penalty = max(0.0, 55.0 - quality_score) * 0.0012
    volatility_penalty = max(0.0, volatility - 2.0) * 0.015
    dynamic_slippage = min(
        cfg["max_slippage_percent"],
        cfg["slippage_percent"] + volatility_penalty + quality_penalty + liquidity_pressure,
    )

    blockers = []
    warnings = []
    if price <= 0:
        blockers.append("invalid_price")
    if spread_percent > cfg["max_spread_percent"]:
        blockers.append("spread_too_high")
    if cfg["liquidity_reject_enabled"] and quote_volume < cfg["min_quote_volume"]:
        blockers.append("liquidity_too_low")
    if quality_score < 35:
        blockers.append("coin_quality_too_low")
    elif quality_score < 50:
        warnings.append("coin_quality_watch")

    spread_cost_score = max(0.0, 100.0 - (spread_percent / max(cfg["max_spread_percent"], 0.01)) * 60.0)
    slippage_cost_score = max(0.0, 100.0 - (dynamic_slippage / max(cfg["max_slippage_percent"], 0.01)) * 60.0)
    liquidity_score = max(0.0, min(100.0, quote_volume / max(cfg["min_quote_volume"], 1.0) * 50.0))
    execution_quality_score = round(
        max(0.0, min(100.0, quality_score * 0.35 + spread_cost_score * 0.25 + slippage_cost_score * 0.25 + liquidity_score * 0.15)),
        2,
    )
    fill_probability = round(max(0.0, min(99.0, execution_quality_score - len(blockers) * 35)), 2)

    return {
        "status": "blocked" if blockers else "ok",
        "blockers": blockers,
        "warnings": warnings,
        "price": price,
        "quote_volume": quote_volume,
        "coin_quality_score": round(quality_score, 2),
        "execution_quality_score": execution_quality_score,
        "fill_probability": fill_probability,
        "spread_percent": round(spread_percent, 4),
        "commission_percent": cfg["commission_percent"],
        "slippage_percent": round(dynamic_slippage, 4),
        "max_spread_percent": cfg["max_spread_percent"],
        "min_quote_volume": cfg["min_quote_volume"],
    }


def simulate_entry(candidate: dict, usdt_size: float, settings: dict) -> dict:
    quality = build_execution_quality(candidate, settings)
    if quality["status"] != "ok":
        return {"status": "rejected", "quality": quality, "reason": ",".join(quality["blockers"])}
    raw_price = quality["price"]
    slip = quality["slippage_percent"] / 100
    commission = quality["commission_percent"] / 100
    executed_price = raw_price * (1 + slip)
    gross_qty = _safe_float(usdt_size) / executed_price if executed_price > 0 else 0
    quantity = gross_qty * (1 - commission)
    commission_usdt = _safe_float(usdt_size) * commission
    return {
        "status": "filled",
        "execution_id": str(uuid4()),
        "side": "BUY",
        "source_price": round(raw_price, 10),
        "executed_price": round(executed_price, 10),
        "quantity": round(quantity, 10),
        "commission_usdt": round(commission_usdt, 6),
        "slippage_percent": quality["slippage_percent"],
        "spread_percent": quality["spread_percent"],
        "execution_quality_score": quality.get("execution_quality_score", 0),
        "fill_probability": quality.get("fill_probability", 0),
        "filled_at": now_iso(),
        "quality": quality,
    }


def simulate_exit(position: dict, current_price: float, settings: dict, reason: str) -> dict:
    cfg = normalize_execution_settings(settings)
    raw_price = _safe_float(current_price)
    slip = cfg["slippage_percent"] / 100
    commission = cfg["commission_percent"] / 100
    executed_price = raw_price * (1 - slip)
    quantity = _safe_float(position.get("quantity"))
    entry = _safe_float(position.get("entry"))
    gross_pnl = (executed_price - entry) * quantity
    commission_usdt = max(0.0, executed_price * quantity * commission)
    net_pnl = gross_pnl - commission_usdt
    execution_quality_score = _safe_float(((position.get("execution_entry") or {}).get("execution_quality_score")), 50.0)
    return {
        "status": "filled",
        "execution_id": str(uuid4()),
        "side": "SELL",
        "source_price": round(raw_price, 10),
        "executed_price": round(executed_price, 10),
        "commission_usdt": round(commission_usdt, 6),
        "slippage_percent": cfg["slippage_percent"],
        "execution_quality_score": round(execution_quality_score, 2),
        "net_pnl": round(net_pnl, 6),
        "gross_pnl": round(gross_pnl, 6),
        "reason": reason,
        "filled_at": now_iso(),
    }
