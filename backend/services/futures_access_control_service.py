from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import now_iso, normalize_permission
ACCESS_LEVELS = ["futures_disabled", "futures_testnet", "futures_read_only", "futures_dry_run", "futures_live_allowed"]

def build_futures_access_control(permission: Dict[str, Any]) -> Dict[str, Any]:
    p=normalize_permission({"futures_permissions":permission})
    if not p.get("futures_enabled"):
        level="futures_disabled"
    elif p.get("futures_real_order_enabled"):
        level="futures_live_allowed"
    elif p.get("futures_environment") == "mainnet":
        level="futures_read_only"
    else:
        level="futures_dry_run" if p.get("futures_enabled") else "futures_testnet"
    return {"service":"futures_access_control","checked_at":now_iso(),"access_levels":ACCESS_LEVELS,"current_access_level":level,"user_can_change":False,"owner_can_change":True,"simple_model":"Kullanıcı sınıfı ayrımı yok; sadece Futures erişim seviyesi yönetilir."}
