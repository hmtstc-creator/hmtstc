from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_models import now_iso

def _num(v: Any, d: float=0.0) -> float:
    try: return float(v)
    except Exception: return d

def build_futures_performance_report(runtime: Dict[str, Any], owner_view: bool=False) -> Dict[str, Any]:
    ledger: List[Dict[str, Any]] = runtime.get("futures_trade_ledger") or runtime.get("futures_ledger") or []
    realized=sum(_num(x.get("realized_pnl"), _num(x.get("pnl"),0)) for x in ledger)
    funding=sum(_num(x.get("funding_fee"),0) for x in ledger)
    fee=sum(_num(x.get("binance_fee"),0) for x in ledger)
    system=sum(_num(x.get("system_buy_commission"),0)+_num(x.get("system_sell_commission"),0) for x in ledger)
    net=sum(_num(x.get("net_user_pnl"), _num(x.get("realized_pnl"),0)-_num(x.get("funding_fee"),0)-_num(x.get("binance_fee"),0)-_num(x.get("system_buy_commission"),0)-_num(x.get("system_sell_commission"),0)) for x in ledger)
    wins=sum(1 for x in ledger if _num(x.get("net_user_pnl"), _num(x.get("realized_pnl"),0))>0)
    losses=sum(1 for x in ledger if _num(x.get("net_user_pnl"), _num(x.get("realized_pnl"),0))<0)
    out={"service":"futures_reporting","checked_at":now_iso(),"periods":["daily","weekly","monthly"],"trade_count":len(ledger),"wins":wins,"losses":losses,"realized_pnl":round(realized,4),"funding_fee":round(funding,4),"binance_fee":round(fee,4),"system_commission":round(system,4),"net_user_pnl":round(net,4),"owner_fields_hidden_for_user":not owner_view}
    if owner_view: out["owner_commission_income"] = round(system,4)
    return out
