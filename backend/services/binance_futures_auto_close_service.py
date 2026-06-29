from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_models import now_iso

def _num(v: Any, d: float=0.0) -> float:
    try: return float(v)
    except Exception: return d

def build_auto_close_decision(position: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context=context or {}
    reasons: List[str] = []
    if _num(position.get("take_profit_hit"),0) or _num(context.get("take_profit_hit"),0): reasons.append("Take profit tetiklendi")
    if _num(position.get("stop_loss_hit"),0) or _num(context.get("stop_loss_hit"),0): reasons.append("Stop loss tetiklendi")
    if _num(context.get("karabasan_score"),80) < 55: reasons.append("Karabasan skoru düştü")
    if _num(context.get("btc_reverse_move_pct"),0) > 1.5: reasons.append("BTC ters yöne sert kırdı")
    if abs(_num(context.get("funding_rate_pct"),0)) > 0.08: reasons.append("Funding riski yükseldi")
    if _num(position.get("liquidation_distance_pct"),99) < 5: reasons.append("Liquidation mesafesi kritik")
    if _num(context.get("daily_loss_usage_pct"),0) >= 85: reasons.append("Günlük zarar limitine yaklaşıldı")
    if abs(_num(context.get("mark_price_deviation_pct"),0)) > .2: reasons.append("Mark price sapması yüksek")
    if context.get("emergency_stop"): reasons.append("Emergency stop aktif")
    return {"service":"binance_futures_auto_close","checked_at":now_iso(),"close_required":bool(reasons),"close_type":"risk_exit" if reasons else "hold", "close_reasons":reasons,"close_preview_only":True,"management":"Otomatik kapatma preview üretir; canlı close gate ayrı owner ve safety kilidiyle yönetilir."}
