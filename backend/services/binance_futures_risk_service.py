from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_models import normalize_permission


def _num(value: Any, default: float) -> float:
    try: return float(value)
    except Exception: return default


def build_futures_risk_settings(permission: Dict[str, Any]) -> Dict[str, Any]:
    p = normalize_permission({"futures_permissions": permission})
    return {
        "max_leverage": p["futures_max_leverage"],
        "margin_type": p["futures_margin_type"],
        "position_mode": p["futures_position_mode"],
        "long_enabled": p["futures_long_enabled"],
        "short_enabled": p["futures_short_enabled"],
        "max_notional_per_trade": p["futures_max_notional_per_trade"],
        "max_open_positions": p["futures_max_open_positions"],
        "daily_loss_limit": p["futures_daily_loss_limit"],
        "tp_sl_required": True,
        "cross_margin_allowed": False,
        "hedge_mode_allowed_phase": False,
    }


def calculate_futures_risk_score(permission: Dict[str, Any], signal: Dict[str, Any] | None = None, runtime: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal = signal or {}
    runtime = runtime or {}
    p = normalize_permission({"futures_permissions": permission})
    leverage = max(1.0, _num(signal.get("leverage"), min(2, p["futures_max_leverage"])))
    stop_loss = _num(signal.get("stop_loss_pct"), 0)
    take_profit = _num(signal.get("take_profit_pct") or signal.get("target_profit_pct"), 0)
    liquidation_distance = _num(signal.get("liquidation_distance_pct"), 12.0 / leverage)
    funding_rate = abs(_num(signal.get("funding_rate_pct"), 0.01))
    mark_deviation = abs(_num(signal.get("mark_price_deviation_pct"), 0.03))
    oi_change = abs(_num(signal.get("open_interest_change_pct"), 4.0))
    long_short_extreme = abs(_num(signal.get("long_short_ratio_bias_pct"), 8.0))
    wick_risk = _num(signal.get("wick_risk"), 25.0)
    margin_safety = _num(signal.get("margin_safety_score"), 78.0)
    notional = _num(signal.get("notional"), min(25.0, p["futures_max_notional_per_trade"]))

    parts = {
        "leverage_risk": max(0, 100 - (leverage - 1) * 15),
        "liquidation_distance": min(100, liquidation_distance * 8),
        "funding_rate": max(0, 100 - funding_rate * 800),
        "open_interest_change": max(0, 100 - oi_change * 3),
        "long_short_ratio": max(0, 100 - long_short_extreme * 2),
        "mark_price_deviation": max(0, 100 - mark_deviation * 450),
        "volatility_wick": max(0, 100 - wick_risk),
        "stop_loss_distance": 90 if stop_loss > 0 else 0,
        "take_profit_presence": 90 if take_profit > 0 else 0,
        "margin_safety": max(0, min(100, margin_safety)),
        "position_size": max(0, 100 - max(0, notional - p["futures_max_notional_per_trade"]) * 4),
    }
    weights = {
        "leverage_risk": .13, "liquidation_distance": .16, "funding_rate": .10, "open_interest_change": .08,
        "long_short_ratio": .07, "mark_price_deviation": .10, "volatility_wick": .08, "stop_loss_distance": .10,
        "take_profit_presence": .08, "margin_safety": .06, "position_size": .04,
    }
    score = round(sum(parts[k] * weights[k] for k in weights), 2)
    return {"futures_risk_score": score, "parts": {k: round(v, 2) for k,v in parts.items()}, "weights": weights}


def futures_hard_blocks(permission: Dict[str, Any], connection: Dict[str, Any], signal: Dict[str, Any] | None = None, open_positions: int = 0, daily_loss: float = 0.0) -> List[str]:
    signal = signal or {}
    p = normalize_permission({"futures_permissions": permission})
    blocks: List[str] = []
    if not p["futures_enabled"]: blocks.append("Futures yetkisi kapalı")
    if not connection.get("connected"): blocks.append("Futures API bağlı değil")
    if connection.get("withdraw_permission"): blocks.append("Withdraw izni açık")
    leverage = int(_num(signal.get("leverage"), p["futures_max_leverage"]))
    if leverage > p["futures_max_leverage"]: blocks.append("Leverage owner limitini aşıyor")
    if p["futures_margin_type"] != "isolated": blocks.append("Margin type isolated değil")
    if p["futures_position_mode"] != "one_way": blocks.append("Position mode one-way değil")
    if _num(signal.get("stop_loss_pct"), 0) <= 0: blocks.append("Stop loss yok")
    if _num(signal.get("take_profit_pct") or signal.get("target_profit_pct"), 0) <= 0: blocks.append("Take profit yok")
    if _num(signal.get("liquidation_distance_pct"), 10) < 5: blocks.append("Liquidation mesafesi yetersiz")
    if abs(_num(signal.get("funding_rate_pct"), 0)) > 0.08: blocks.append("Funding rate aşırı riskli")
    if abs(_num(signal.get("mark_price_deviation_pct"), 0)) > 0.2: blocks.append("Mark price sapması yüksek")
    if open_positions >= int(p["futures_max_open_positions"]): blocks.append("Açık Futures pozisyon limiti dolu")
    if abs(daily_loss) >= float(p["futures_daily_loss_limit"]): blocks.append("Günlük Futures zarar limiti dolu")
    side = str(signal.get("side") or "long").lower()
    if side == "short" and not p["futures_short_enabled"]: blocks.append("Short kapalıyken short sinyali geldi")
    return blocks
