from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import now_iso

def build_bot_state_recovery_plan(runtime: Dict[str, Any]) -> Dict[str, Any]:
    return {"service":"bot_state_recovery","checked_at":now_iso(),"recover_bot_mode":runtime.get("bot_control_mode","closed"),"reload_open_positions":True,"reload_futures_permissions":True,"real_orders_remain_locked_after_restart":True,"management":"VPS restart sonrası bot state korunur ama gerçek emir kilidi owner açmadan aktif olmaz."}
