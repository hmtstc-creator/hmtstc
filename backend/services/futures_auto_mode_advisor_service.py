from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_karabasan_service import build_karabasan_futures_score
from services.binance_futures_models import now_iso

def _num(v: Any, d: float) -> float:
    try: return float(v)
    except Exception: return d

def build_futures_auto_mode_advice(runtime: Dict[str, Any], settings: Dict[str, Any], permission: Dict[str, Any], connection: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context = context or {}
    gate = build_karabasan_futures_score(runtime, settings, permission, connection, context)
    indicators = {
        "trend": _num(context.get("trend_score"), gate.get("karabasan_spot_score", 70)),
        "liquidation_safety": _num(context.get("liquidation_safety_score"), 75),
        "volatility": _num(context.get("volatility_score"), 68),
        "funding": _num(context.get("funding_score"), 72),
        "position_size": _num(context.get("position_size_score"), 80),
        "historical_quality": _num(context.get("historical_quality_score"), 65),
    }
    confidence = round(sum(indicators.values()) / len(indicators), 2)
    advice = "trade_allowed" if confidence >= 75 and gate.get("decision") == "allow" else ("wait" if confidence >= 55 else "block")
    return {"service":"futures_auto_mode_advisor","checked_at":now_iso(),"auto_advice":advice,"confidence":confidence,"indicators":indicators,"final_authority":"Karabasan + Futures Risk Gate", "ai_can_submit_order": False, "reason": "AI sadece öneri üretir; canlı emir yetkisi yoktur."}
