from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_models import now_iso

def _num(v: Any, d: float=0.0) -> float:
    try: return float(v)
    except Exception: return d

def build_futures_alarms(runtime: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context=context or {}; alarms: List[Dict[str, Any]]=[]
    def add(sev,t,msg): alarms.append({"severity":sev,"type":t,"message":msg})
    if _num(context.get("liquidation_distance_pct"),99) < 5: add("critical","liquidation_distance_low","Liquidation mesafesi kritik seviyeye düştü.")
    if abs(_num(context.get("funding_rate_pct"),0)) > .08: add("high","funding_rate_high","Funding rate anormal yükseldi.")
    if abs(_num(context.get("mark_price_deviation_pct"),0)) > .2: add("high","mark_price_deviation","Mark price sapması arttı.")
    if _num(context.get("karabasan_score"),80) < 55: add("high","karabasan_score_drop","Karabasan Futures skoru düştü.")
    if context.get("api_connected") is False: add("critical","api_disconnected","Futures API bağlantısı koptu.")
    if _num(context.get("daily_loss_usage_pct"),0) > 85: add("critical","daily_loss_limit_near","Günlük zarar limitine yaklaşıldı.")
    if context.get("emergency_stop"): add("critical","emergency_stop","Emergency stop aktif.")
    return {"service":"futures_alarm_service","checked_at":now_iso(),"alarm_count":len(alarms),"alarms":alarms,"new_trade_allowed":not any(a['severity']=='critical' for a in alarms),"user_message":"Risk uyarısı var." if alarms else "Futures alarm yok.","admin_detail_enabled":True}
