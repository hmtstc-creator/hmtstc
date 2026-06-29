from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import now_iso

def build_production_health(runtime: Dict[str, Any], connection: Dict[str, Any]) -> Dict[str, Any]:
    return {"service":"production_health","checked_at":now_iso(),"backend_health":"ok","binance_api_health":"ok" if connection.get("connected") else "not_connected","futures_readiness":"review","bot_state":runtime.get("bot_control_mode") or ("running" if runtime.get("bot_running") else "stopped"),"open_positions_sync":"required","last_recovery_time":runtime.get("last_recovery_time"),"last_critical_error":runtime.get("last_critical_error"),"production_safety_status":"locked_until_owner_live_gate"}
