from __future__ import annotations
from typing import Dict, Any
from services.binance_futures_models import now_iso

def build_rate_limit_policy(weight_used: int = 0, order_count: int = 0) -> Dict[str, Any]:
    blocked = weight_used > 2200 or order_count > 900
    return {"service":"binance_rate_limit_policy","checked_at":now_iso(),"weight_used":weight_used,"order_count":order_count,"retry_backoff_enabled":True,"new_order_temporarily_blocked":blocked,"management":"Rate limit yükselirse emir denemesi durur, retry/backoff devreye girer."}
