from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import now_iso, normalize_permission

def _num(v: Any, d: float) -> float:
    try: return float(v)
    except Exception: return d

def build_karabasan_futures_short_score(permission: Dict[str, Any], market: Dict[str, Any] | None = None) -> Dict[str, Any]:
    market = market or {}
    p = normalize_permission({"futures_permissions": permission})
    parts = {
        "btc_downtrend": _num(market.get("btc_downtrend_score"), 65),
        "market_weakness": _num(market.get("market_weakness_score"), 62),
        "total2_weakness": _num(market.get("total2_weakness_score"), 60),
        "coin_relative_weakness": _num(market.get("coin_relative_weakness_score"), 66),
        "dominance_pressure": _num(market.get("dominance_pressure_score"), 58),
        "funding_safety": _num(market.get("funding_safety_score"), 70),
        "short_squeeze_risk": 100 - _num(market.get("short_squeeze_risk"), 30),
        "liquidity": _num(market.get("liquidity_score"), 72),
        "stop_distance": _num(market.get("stop_distance_score"), 75),
    }
    weights = {"btc_downtrend": .16, "market_weakness": .13, "total2_weakness": .10, "coin_relative_weakness": .16, "dominance_pressure": .08, "funding_safety": .10, "short_squeeze_risk": .12, "liquidity": .08, "stop_distance": .07}
    score = round(sum(parts[k] * weights[k] for k in weights), 2)
    blocks = []
    if not p.get("futures_short_enabled"):
        blocks.append("Short owner izni kapalı")
    if score < 65:
        blocks.append("Short Karabasan skoru 65 altında")
    decision = "allow" if not blocks else "blocked"
    return {"service":"karabasan_futures_short_score","checked_at":now_iso(),"side":"short","short_score":score,"decision":decision,"parts":parts,"blocking_reasons":blocks,"management":"Short, long ile aynı gate üzerinden değil ayrı zayıflık/skoru ve squeeze riskiyle yönetilir."}
