from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_models import now_iso

def _num(v: Any, d: float=0.0) -> float:
    try: return float(v)
    except Exception: return d

def build_owner_finance_panel(runtime: Dict[str, Any]) -> Dict[str, Any]:
    spot: List[Dict[str, Any]] = runtime.get("spot_trade_ledger") or runtime.get("trade_ledger") or []
    fut: List[Dict[str, Any]] = runtime.get("futures_trade_ledger") or runtime.get("futures_ledger") or []
    payments: List[Dict[str, Any]] = runtime.get("payment_collection_log") or []
    spot_income=sum(_num(x.get("owner_commission_income"), _num(x.get("system_commission"),0)) for x in spot)
    futures_income=sum(_num(x.get("owner_commission_income"), _num(x.get("system_buy_commission"),0)+_num(x.get("system_sell_commission"),0)) for x in fut)
    paid=sum(_num(x.get("amount"),0) for x in payments if str(x.get("status") or '').lower() in {'paid','collected','tahsil_edildi'})
    total=spot_income+futures_income
    return {"service":"owner_finance_panel","checked_at":now_iso(),"spot_commission_income":round(spot_income,4),"futures_commission_income":round(futures_income,4),"total_receivable":round(total,4),"paid_amount":round(paid,4),"pending_amount":round(max(0,total-paid),4),"payment_methods":["manual","USDT","IBAN"],"withdraw_permission_required":False,"management":"Tahsilat manuel işaretlenir; kullanıcı owner gelir detayını görmez."}
