from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_models import now_iso

def _num(v: Any, d: float=0.0) -> float:
    try: return float(v)
    except Exception: return d

def build_live_position_monitor(runtime: Dict[str, Any]) -> Dict[str, Any]:
    positions: List[Dict[str, Any]] = runtime.get("futures_open_positions") or runtime.get("futures_positions") or []
    cards=[]
    for p in positions:
        entry=_num(p.get("entry_price"),0); mark=_num(p.get("mark_price"),entry); liq=_num(p.get("liquidation_price"),0)
        side=str(p.get("side") or "long").lower()
        pnl=_num(p.get("unrealized_pnl"),(mark-entry)*(1 if side=='long' else -1))
        distance=abs((mark-liq)/mark*100) if mark and liq else _num(p.get("liquidation_distance_pct"),99)
        status="safe" if distance>=10 else ("warning" if distance>=5 else "critical")
        cards.append({**p,"unrealized_pnl":round(pnl,4),"liquidation_distance_pct":round(distance,2),"risk_status":status,"position_age":p.get("position_age") or p.get("opened_at") or "unknown"})
    return {"service":"binance_futures_live_position_monitor","checked_at":now_iso(),"polling_hint_seconds":5,"position_count":len(cards),"positions":cards,"monitor_required_for_live":True,"management":"Pozisyon izleme aktif değilse Futures live gate açılmaz."}
