from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_models import normalize_permission, now_iso, BINANCE_FUTURES_OFFICIAL_ENDPOINTS

def build_position_mode_policy(permission: Dict[str, Any], requested_mode: str | None = None) -> Dict[str, Any]:
    p = normalize_permission({"futures_permissions": permission})
    requested = str(requested_mode or p.get("futures_position_mode") or "one_way").lower().replace('-', '_')
    hedge_requested = requested in {"hedge", "hedge_mode"}
    hedge_owner_enabled = bool(p.get("hedge_mode_enabled", False))
    allowed = (not hedge_requested) or hedge_owner_enabled
    return {
        "service": "binance_futures_position_mode_policy",
        "checked_at": now_iso(),
        "default_mode": "one_way",
        "requested_mode": "hedge" if hedge_requested else "one_way",
        "effective_mode": "hedge" if hedge_requested and allowed else "one_way",
        "hedge_mode_allowed": allowed and hedge_requested,
        "position_mode_endpoint": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["change_position_mode"],
        "risk_rule": "Hedge mode açılırsa long ve short skorları ayrı üretilir; default one-way korunur.",
        "blocking_reasons": [] if allowed else ["Hedge mode owner tarafından açılmadı"],
    }
